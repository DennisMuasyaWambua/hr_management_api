from __future__ import annotations

import datetime
from uuid import UUID

from django.utils import timezone

from ..dataclasses import ActionCategory, ActionItem, ActionPriority
from ..generators.base import BaseActionGenerator
from ..services import register_generator

_BG_CHECK_GRACE_DAYS = 3
_DOC_VERIFICATION_GRACE_DAYS = 2
_ONBOARDING_WINDOW_DAYS = 90  # only flag docs for employees hired within this window


@register_generator
class OnboardingActionGenerator(BaseActionGenerator):
    category = ActionCategory.ONBOARDING.value

    def generate(self) -> list[ActionItem]:
        from apps.hr.models import BackgroundCheck, EmployeeOnboardingDocument
        from apps.payroll.models import EmployeeProfile

        now = timezone.now()
        today = now.date()
        items: list[ActionItem] = []

        # Q1: Recent employee IDs (hired within onboarding window, still active)
        hire_threshold = today - datetime.timedelta(days=_ONBOARDING_WINDOW_DAYS)
        employee_qs = EmployeeProfile.objects.filter(
            company_id=self.company_id,
            is_deleted=False,
            employment_status='active',
            start_date__gte=hire_threshold,
        ).values('id', 'start_date', 'job_title', 'employee_number')

        if self.employee_ids is not None:
            employee_qs = employee_qs.filter(id__in=self.employee_ids)

        recent_employee_map = {str(e['id']): e for e in employee_qs}
        if not recent_employee_map:
            return []

        recent_ids = list(recent_employee_map.keys())

        # Q2: Onboarding documents missing or awaiting verification
        doc_threshold = now - datetime.timedelta(days=_DOC_VERIFICATION_GRACE_DAYS)
        doc_qs = EmployeeOnboardingDocument.objects.filter(
            employee_id__in=recent_ids,
            status__in=['missing', 'uploaded'],
        ).values('id', 'employee_id', 'doc_type', 'status', 'updated_at')

        for doc in doc_qs:
            emp_id = str(doc['employee_id'])
            emp = recent_employee_map.get(emp_id, {})

            if doc['status'] == 'missing':
                action_type = 'DOCUMENT_MISSING'
                priority = ActionPriority.HIGH
                age_hours = (now - datetime.datetime.combine(
                    emp.get('start_date', today), datetime.time.min,
                    tzinfo=datetime.timezone.utc,
                )).total_seconds() / 3600
                description = (
                    f'{doc["doc_type"].replace("_", " ").upper()} document not yet uploaded.'
                )
            else:  # uploaded
                if doc['updated_at'] < doc_threshold:
                    action_type = 'DOCUMENT_AWAITING_VERIFICATION'
                    priority = ActionPriority.MEDIUM
                    age_hours = (now - doc['updated_at']).total_seconds() / 3600
                    description = (
                        f'{doc["doc_type"].replace("_", " ").upper()} uploaded '
                        f'{int(age_hours // 24)} days ago — verification pending.'
                    )
                else:
                    continue  # uploaded recently, within grace period

            items.append(ActionItem(
                id=self.make_id('onboarding', str(doc['id']), action_type),
                action_type=action_type,
                category=ActionCategory.ONBOARDING,
                priority=priority,
                title=f'{action_type.replace("_", " ").title()}: {doc["doc_type"].replace("_", " ").upper()}',
                description=description,
                source_module='onboarding',
                source_record_id=str(doc['id']),
                action_url=f'/hr/onboarding/{emp_id}/',
                age_hours=round(age_hours, 1),
                employee_id=emp_id,
                metadata={
                    'doc_type': doc['doc_type'],
                    'status': doc['status'],
                    'employee_number': emp.get('employee_number', ''),
                },
            ))

        # Q3: Background checks pending > 3 days or flagged
        bg_grace = now - datetime.timedelta(days=_BG_CHECK_GRACE_DAYS)
        bg_qs = BackgroundCheck.objects.filter(
            company_id=self.company_id,
            is_deleted=False,
        ).filter(
            status__in=['pending', 'in_progress'],
            requested_at__lt=bg_grace,
        ).values(
            'id', 'employee_id', 'candidate_id', 'check_type', 'status', 'requested_at',
        )

        for bg in bg_qs:
            if self.employee_ids is not None and bg['employee_id'] not in self.employee_ids:
                continue
            age_hours = (now - bg['requested_at']).total_seconds() / 3600
            items.append(ActionItem(
                id=self.make_id('onboarding', str(bg['id']), 'BACKGROUND_CHECK_PENDING'),
                action_type='BACKGROUND_CHECK_PENDING',
                category=ActionCategory.ONBOARDING,
                priority=ActionPriority.MEDIUM,
                title=f'Background check pending: {bg["check_type"].replace("_", " ").title()}',
                description=(
                    f'{bg["check_type"].replace("_", " ").title()} check submitted '
                    f'{int(age_hours // 24)} days ago — no result yet.'
                ),
                source_module='onboarding',
                source_record_id=str(bg['id']),
                action_url=f'/hr/background-checks/{bg["id"]}/',
                age_hours=round(age_hours, 1),
                employee_id=str(bg['employee_id']) if bg['employee_id'] else None,
                candidate_id=str(bg['candidate_id']) if bg['candidate_id'] else None,
                metadata={'check_type': bg['check_type'], 'status': bg['status']},
            ))

        return items
