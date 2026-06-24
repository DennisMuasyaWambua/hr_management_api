from __future__ import annotations

import datetime
from uuid import UUID

from django.utils import timezone

from apps.hr.models import LeaveBalance, LeaveRecall, LeaveRequest
from ..dataclasses import ActionCategory, ActionItem, ActionPriority
from ..generators.base import BaseActionGenerator
from ..services import register_generator

_PENDING_GRACE_HOURS = 4
_LOW_BALANCE_THRESHOLD = 3  # days — annual leave below this is flagged


@register_generator
class LeaveActionGenerator(BaseActionGenerator):
    category = ActionCategory.LEAVE.value

    def generate(self) -> list[ActionItem]:
        now = timezone.now()
        grace_threshold = now - datetime.timedelta(hours=_PENDING_GRACE_HOURS)
        items: list[ActionItem] = []

        # Q1: Leave requests pending approval > 4 hours
        pending_leaves = LeaveRequest.objects.filter(
            company_id=self.company_id,
            status='pending',
            created_at__lt=grace_threshold,
            is_deleted=False,
        ).values(
            'id', 'employee_id', 'leave_type', 'start_date', 'end_date',
            'days_requested', 'created_at',
        )

        for lr in pending_leaves:
            if self.employee_ids is not None and lr['employee_id'] not in self.employee_ids:
                continue
            age_hours = (now - lr['created_at']).total_seconds() / 3600
            priority = ActionPriority.HIGH if age_hours > 24 else ActionPriority.MEDIUM
            items.append(ActionItem(
                id=self.make_id('leave', str(lr['id']), 'LEAVE_PENDING_APPROVAL'),
                action_type='LEAVE_PENDING_APPROVAL',
                category=ActionCategory.LEAVE,
                priority=priority,
                title='Leave request pending approval',
                description=(
                    f'{lr["leave_type"].replace("_", " ").title()} leave '
                    f'({lr["start_date"]} to {lr["end_date"]}, {lr["days_requested"]} days) '
                    f'waiting {int(age_hours)}h.'
                ),
                source_module='leave',
                source_record_id=str(lr['id']),
                action_url=f'/hr/leaves/{lr["id"]}/',
                due_date=lr['created_at'] + datetime.timedelta(hours=24),
                age_hours=round(age_hours, 1),
                employee_id=str(lr['employee_id']),
                metadata={
                    'leave_type': lr['leave_type'],
                    'start_date': str(lr['start_date']),
                    'end_date': str(lr['end_date']),
                    'days_requested': float(lr['days_requested']),
                },
            ))

        # Q2: Leave recalls pending > 4 hours
        pending_recalls = LeaveRecall.objects.filter(
            company_id=self.company_id,
            status='pending',
            created_at__lt=grace_threshold,
        ).values('id', 'employee_id', 'resume_date', 'created_at', 'reason')

        for rc in pending_recalls:
            if self.employee_ids is not None and rc['employee_id'] not in self.employee_ids:
                continue
            age_hours = (now - rc['created_at']).total_seconds() / 3600
            items.append(ActionItem(
                id=self.make_id('leave', str(rc['id']), 'LEAVE_RECALL_PENDING'),
                action_type='LEAVE_RECALL_PENDING',
                category=ActionCategory.LEAVE,
                priority=ActionPriority.HIGH,
                title='Leave recall pending approval',
                description=(
                    f'Recall request (resume {rc["resume_date"]}) '
                    f'waiting {int(age_hours)}h for sign-off.'
                ),
                source_module='leave',
                source_record_id=str(rc['id']),
                action_url=f'/hr/leave-recalls/{rc["id"]}/',
                due_date=rc['created_at'] + datetime.timedelta(hours=24),
                age_hours=round(age_hours, 1),
                employee_id=str(rc['employee_id']),
                metadata={'resume_date': str(rc['resume_date'])},
            ))

        # Q3: Low annual leave balance for current year
        current_year = now.year
        low_balances = LeaveBalance.objects.filter(
            company_id=self.company_id,
            year=current_year,
            leave_type='annual',
            remaining_days__lt=_LOW_BALANCE_THRESHOLD,
            is_deleted=False,
        ).values('id', 'employee_id', 'remaining_days', 'total_days', 'updated_at')

        for lb in low_balances:
            if self.employee_ids is not None and lb['employee_id'] not in self.employee_ids:
                continue
            items.append(ActionItem(
                id=self.make_id('leave', str(lb['id']), 'LOW_LEAVE_BALANCE'),
                action_type='LOW_LEAVE_BALANCE',
                category=ActionCategory.LEAVE,
                priority=ActionPriority.LOW,
                title='Low annual leave balance',
                description=(
                    f'{float(lb["remaining_days"]):.1f} day(s) of annual leave '
                    f'remaining out of {float(lb["total_days"]):.1f}.'
                ),
                source_module='leave',
                source_record_id=str(lb['id']),
                action_url=f'/hr/leave-balances/{lb["id"]}/',
                age_hours=0.0,
                employee_id=str(lb['employee_id']),
                metadata={
                    'remaining_days': float(lb['remaining_days']),
                    'total_days': float(lb['total_days']),
                    'year': current_year,
                },
            ))

        return items
