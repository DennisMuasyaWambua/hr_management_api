from __future__ import annotations

import copy
import logging
from typing import Optional
from uuid import UUID

from django.utils import timezone

from .dataclasses import ActionCategory, ActionItem, ActionPriority, ActionStatus
from .models import ActionRecord
from .priority import PriorityEngine

logger = logging.getLogger(__name__)

CACHE_TTL = 300  # seconds — matches action spec
_GENERATOR_REGISTRY: list[type] = []


def register_generator(cls: type) -> type:
    """Class decorator — registers a generator class. Applied at module import time."""
    _GENERATOR_REGISTRY.append(cls)
    return cls


# ── Cache helpers (fail-safe) ────────────────────────────────────────────────

def _cache_key(company_id: UUID | str, suffix: str) -> str:
    return f'actions:{company_id}:{suffix}'


def _cache_get(key: str):
    try:
        from django.core.cache import cache
        return cache.get(key)
    except Exception:
        return None


def _cache_set(key: str, value, ttl: int = CACHE_TTL) -> None:
    try:
        from django.core.cache import cache
        cache.set(key, value, ttl)
    except Exception:
        pass


def _cache_delete(*keys: str) -> None:
    try:
        from django.core.cache import cache
        cache.delete_many(list(keys))
    except Exception:
        pass


# ── Service ──────────────────────────────────────────────────────────────────

class ActionCenterService:
    """
    Aggregates generated actions from all registered generators for a company.

    Generator results are cached per company (TTL 300s).
    ActionRecord overlays (dismissed/escalated state) are always loaded fresh.
    """

    def __init__(self, company_id: UUID | str, employee_ids: Optional[list[UUID]] = None):
        self.company_id = company_id
        self.employee_ids = employee_ids

    # ── Internal ────────────────────────────────────────────────────────────

    def _generate(self) -> list[ActionItem]:
        """Run all generators, score, and cache. Returns scored items (no overlay)."""
        key = _cache_key(self.company_id, 'generated')
        cached = _cache_get(key)
        if cached is not None:
            return cached
        raw: list[ActionItem] = []
        for gen_cls in _GENERATOR_REGISTRY:
            gen = gen_cls(company_id=self.company_id, employee_ids=self.employee_ids)
            raw.extend(gen.safe_generate())
        for item in raw:
            PriorityEngine.enrich(item)
        _cache_set(key, raw)
        return raw

    def _load_overlays(self, ids: list[str]) -> dict[str, ActionRecord]:
        if not ids:
            return {}
        return {r.id: r for r in ActionRecord.objects.filter(
            id__in=ids, company_id=self.company_id,
        )}

    @staticmethod
    def _apply_overlay(item: ActionItem, record: Optional[ActionRecord]) -> None:
        if record is None:
            return
        item.first_seen_at = record.first_seen_at
        if record.dismissed_at is not None:
            item.status = ActionStatus.DISMISSED
            item.dismissed_at = record.dismissed_at
        if record.escalated_at is not None:
            item.status = ActionStatus.ESCALATED
            item.escalated_at = record.escalated_at

    def _build_items(self) -> list[ActionItem]:
        """Generate + shallow-copy + overlay. Always returns fresh overlay state."""
        raw = self._generate()
        items = [copy.copy(i) for i in raw]  # don't mutate cached objects
        overlays = self._load_overlays([i.id for i in items])
        for item in items:
            self._apply_overlay(item, overlays.get(item.id))
        return items

    # ── Public API ───────────────────────────────────────────────────────────

    def get_actions(
        self,
        category: Optional[str] = None,
        priority: Optional[str] = None,
        status_filter: str = 'active',
        overdue_only: bool = False,
    ) -> list[ActionItem]:
        items = self._build_items()
        now = timezone.now()

        if category:
            items = [i for i in items if i.category.value == category]
        if priority:
            items = [i for i in items if i.priority.value == priority]
        if overdue_only:
            items = [i for i in items if i.due_date and i.due_date < now]

        _status_map = {
            'active': ActionStatus.ACTIVE,
            'dismissed': ActionStatus.DISMISSED,
            'escalated': ActionStatus.ESCALATED,
        }
        target = _status_map.get(status_filter, ActionStatus.ACTIVE)
        items = [i for i in items if i.status == target]
        items.sort(key=lambda i: i.priority_score, reverse=True)
        return items

    def get_summary(self) -> dict:
        key = _cache_key(self.company_id, 'summary')
        cached = _cache_get(key)
        if cached is not None:
            return cached
        items = self.get_actions(status_filter='active')
        now = timezone.now()
        by_priority: dict[str, int] = {p.value: 0 for p in ActionPriority}
        by_category: dict[str, int] = {c.value: 0 for c in ActionCategory}
        overdue = 0
        for item in items:
            by_priority[item.priority.value] += 1
            by_category[item.category.value] += 1
            if item.due_date and item.due_date < now:
                overdue += 1
        result = {
            'total_active': len(items),
            'overdue': overdue,
            'by_priority': by_priority,
            'by_category': by_category,
            'generated_at': now.isoformat(),
        }
        _cache_set(key, result)
        return result

    def get_high_priority(self) -> list[ActionItem]:
        items = self.get_actions(status_filter='active')
        return [i for i in items if i.priority.value in ('critical', 'high')][:20]

    def get_overdue(self, category: Optional[str] = None) -> list[ActionItem]:
        items = self.get_actions(category=category, overdue_only=True)
        items.sort(key=lambda i: i.age_hours, reverse=True)
        return items

    def get_upcoming(self, days: int = 7, category: Optional[str] = None) -> list[ActionItem]:
        import datetime as _dt
        horizon = timezone.now() + _dt.timedelta(days=days)
        items = self.get_actions(category=category, status_filter='active')
        upcoming = [i for i in items if i.due_date and i.due_date <= horizon]
        upcoming.sort(key=lambda i: i.due_date)  # type: ignore[arg-type]
        return upcoming

    def dismiss(self, action_id: str, user_id: Optional[str], reason: str = '') -> ActionRecord:
        record, _ = ActionRecord.objects.get_or_create(
            id=action_id, defaults={'company_id': self.company_id},
        )
        record.dismissed_at = timezone.now()
        record.dismissed_by = user_id
        record.dismiss_reason = reason
        record.save(update_fields=['dismissed_at', 'dismissed_by', 'dismiss_reason', 'updated_at'])
        _cache_delete(
            _cache_key(self.company_id, 'summary'),
        )
        return record

    def escalate(self, action_id: str, user_id: Optional[str], note: str = '') -> ActionRecord:
        record, _ = ActionRecord.objects.get_or_create(
            id=action_id, defaults={'company_id': self.company_id},
        )
        record.escalated_at = timezone.now()
        record.escalated_by = user_id
        record.escalate_note = note
        record.save(update_fields=['escalated_at', 'escalated_by', 'escalate_note', 'updated_at'])
        _cache_delete(
            _cache_key(self.company_id, 'summary'),
        )
        self._send_escalation_notification(action_id, note)
        return record

    def refresh(self) -> None:
        """Invalidate all cached data for this company, forcing next request to regenerate."""
        _cache_delete(
            _cache_key(self.company_id, 'generated'),
            _cache_key(self.company_id, 'summary'),
        )

    def _send_escalation_notification(self, action_id: str, note: str) -> None:
        try:
            from apps.core.models import Company
            from apps.core.services import notifications as notif
            company = Company.objects.filter(id=self.company_id).values(
                'contact_email', 'name',
            ).first()
            if not company or not company['contact_email']:
                return
            notif.notify(
                'action.escalated',
                [{'email': company['contact_email']}],
                {
                    'action_id': action_id,
                    'company_name': company['name'],
                    'note': note or 'No note provided.',
                },
                company_id=self.company_id,
                related=('ActionRecord', action_id),
            )
        except Exception:
            logger.warning(
                'action.escalated notification failed for action %s company %s',
                action_id, self.company_id, exc_info=True,
            )
