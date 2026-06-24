from __future__ import annotations

import datetime
from uuid import UUID

from django.utils import timezone

from apps.hr.models import EmployeeExit
from ..dataclasses import ActionCategory, ActionItem, ActionPriority
from ..generators.base import BaseActionGenerator
from ..services import register_generator

_CLEARANCE_STALL_DAYS = 3
_FINAL_DUES_STALL_DAYS = 2


@register_generator
class OffboardingActionGenerator(BaseActionGenerator):
    category = ActionCategory.OFFBOARDING.value

    def generate(self) -> list[ActionItem]:
        now = timezone.now()
        today = now.date()
        items: list[ActionItem] = []

        clearance_stall_threshold = now - datetime.timedelta(days=_CLEARANCE_STALL_DAYS)
        final_dues_stall_threshold = now - datetime.timedelta(days=_FINAL_DUES_STALL_DAYS)

        # Q1: Active exits with their clearance record (single LEFT JOIN via select_related)
        exit_qs = EmployeeExit.objects.filter(
            company_id=self.company_id,
            status__in=['initiated', 'clearance', 'final_dues'],
        ).select_related('clearance')

        if self.employee_ids is not None:
            exit_qs = exit_qs.filter(employee_id__in=self.employee_ids)

        for ex in exit_qs:
            emp_id = str(ex.employee_id)

            if ex.status == 'clearance':
                # EXIT_CLEARANCE_STALLED: clearance in progress but stalled
                try:
                    clr = ex.clearance
                except Exception:
                    clr = None

                if clr and clr.status in ('pending', 'in_progress') and clr.created_at < clearance_stall_threshold:
                    pending_depts = [
                        dept for dept, cleared in [
                            ('IT', clr.it_cleared),
                            ('Finance', clr.finance_cleared),
                            ('Admin', clr.admin_cleared),
                            ('HR', clr.hr_cleared),
                            ('Manager', clr.manager_cleared),
                        ]
                        if not cleared
                    ]
                    age_hours = (now - clr.created_at).total_seconds() / 3600
                    items.append(ActionItem(
                        id=self.make_id('offboarding', str(ex.id), 'EXIT_CLEARANCE_STALLED'),
                        action_type='EXIT_CLEARANCE_STALLED',
                        category=ActionCategory.OFFBOARDING,
                        priority=ActionPriority.HIGH,
                        title='Exit clearance stalled',
                        description=(
                            f'Clearance stalled for {int(age_hours // 24)} days. '
                            f'Pending sign-offs: {", ".join(pending_depts) or "unknown"}.'
                        ),
                        source_module='offboarding',
                        source_record_id=str(ex.id),
                        action_url=f'/hr/exits/{ex.id}/',
                        age_hours=round(age_hours, 1),
                        employee_id=emp_id,
                        metadata={
                            'exit_kind': ex.kind,
                            'pending_departments': pending_depts,
                            'clearance_status': clr.status,
                        },
                    ))

            # EXIT_OVERDUE: last working day has passed but exit not completed
            if ex.last_working_day and ex.last_working_day < today:
                days_overdue = (today - ex.last_working_day).days
                priority = ActionPriority.CRITICAL if days_overdue > 7 else ActionPriority.HIGH
                items.append(ActionItem(
                    id=self.make_id('offboarding', str(ex.id), 'EXIT_OVERDUE'),
                    action_type='EXIT_OVERDUE',
                    category=ActionCategory.OFFBOARDING,
                    priority=priority,
                    title='Exit process overdue',
                    description=(
                        f'Last working day was {ex.last_working_day} '
                        f'({days_overdue} day(s) ago). Status still: {ex.status}.'
                    ),
                    source_module='offboarding',
                    source_record_id=str(ex.id),
                    action_url=f'/hr/exits/{ex.id}/',
                    due_date=datetime.datetime.combine(
                        ex.last_working_day, datetime.time(17, 0),
                        tzinfo=datetime.timezone.utc,
                    ),
                    age_hours=days_overdue * 24.0,
                    employee_id=emp_id,
                    metadata={
                        'exit_kind': ex.kind,
                        'last_working_day': str(ex.last_working_day),
                        'days_overdue': days_overdue,
                    },
                ))

            # FINAL_DUES_PENDING: in final_dues stage but payment not recorded
            if ex.status == 'final_dues' and ex.final_dues_paid_at is None:
                if ex.updated_at < final_dues_stall_threshold:
                    age_hours = (now - ex.updated_at).total_seconds() / 3600
                    items.append(ActionItem(
                        id=self.make_id('offboarding', str(ex.id), 'FINAL_DUES_PENDING'),
                        action_type='FINAL_DUES_PENDING',
                        category=ActionCategory.OFFBOARDING,
                        priority=ActionPriority.HIGH,
                        title='Final dues payment pending',
                        description=(
                            f'Final dues not marked as paid. '
                            f'Status has been "final_dues" for {int(age_hours // 24)} days.'
                        ),
                        source_module='offboarding',
                        source_record_id=str(ex.id),
                        action_url=f'/hr/exits/{ex.id}/',
                        age_hours=round(age_hours, 1),
                        employee_id=emp_id,
                        metadata={
                            'exit_kind': ex.kind,
                            'final_dues_total': (
                                float(ex.final_dues_total)
                                if ex.final_dues_total is not None
                                else None
                            ),
                        },
                    ))

        return items
