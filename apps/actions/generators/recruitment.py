from __future__ import annotations

import datetime
from typing import Optional
from uuid import UUID

from django.db.models import Q
from django.utils import timezone

from apps.recruitment.models import Candidate, Interview, JobPosting
from ..dataclasses import ActionCategory, ActionItem, ActionPriority
from ..generators.base import BaseActionGenerator
from ..services import register_generator


@register_generator
class RecruitmentActionGenerator(BaseActionGenerator):
    category = ActionCategory.RECRUITMENT.value

    def generate(self) -> list[ActionItem]:
        now = timezone.now()
        today = now.date()
        items: list[ActionItem] = []

        # Q1: Scheduled interviews with no outcome recorded and past due
        interview_qs = Interview.objects.filter(
            company_id=self.company_id,
            status='scheduled',
            scheduled_at__lt=now,
        ).select_related('candidate', 'job_posting')

        for iv in interview_qs:
            age_hours = (now - iv.scheduled_at).total_seconds() / 3600
            priority = ActionPriority.CRITICAL if age_hours > 48 else ActionPriority.HIGH
            items.append(ActionItem(
                id=self.make_id('recruitment', str(iv.id), 'INTERVIEW_OVERDUE'),
                action_type='INTERVIEW_OVERDUE',
                category=ActionCategory.RECRUITMENT,
                priority=priority,
                title=f'Overdue interview: {iv.candidate.full_name}',
                description=(
                    f'{iv.get_interview_type_display()} interview scheduled '
                    f'{iv.scheduled_at.strftime("%d %b %Y %H:%M")} — no outcome recorded.'
                ),
                source_module='recruitment',
                source_record_id=str(iv.id),
                action_url=f'/recruitment/interviews/{iv.id}/',
                due_date=iv.scheduled_at,
                age_hours=round(age_hours, 1),
                candidate_id=str(iv.candidate_id),
                metadata={
                    'interview_type': iv.interview_type,
                    'job_title': iv.job_posting.title,
                },
            ))

        # Q2: Stalled pipeline candidates AND offer awaiting response (combined)
        stale_threshold = now - datetime.timedelta(days=14)
        offer_threshold = now - datetime.timedelta(days=5)

        candidate_qs = Candidate.objects.filter(
            company_id=self.company_id,
            is_deleted=False,
        ).filter(
            Q(
                current_stage__in=['screened', 'interview_l1', 'interview_l2'],
                updated_at__lt=stale_threshold,
            ) | Q(
                current_stage='offer_sent',
                updated_at__lt=offer_threshold,
            )
        ).values('id', 'full_name', 'current_stage', 'updated_at')

        for c in candidate_qs:
            age_hours = (now - c['updated_at']).total_seconds() / 3600
            if c['current_stage'] == 'offer_sent':
                action_type = 'OFFER_AWAITING_RESPONSE'
                priority = ActionPriority.HIGH
                title = f'Offer awaiting response: {c["full_name"]}'
                description = f'Offer sent {int(age_hours // 24)} days ago with no reply.'
                due_at = c['updated_at'] + datetime.timedelta(days=5)
            else:
                action_type = 'PIPELINE_STALLED'
                priority = ActionPriority.MEDIUM
                title = f'Pipeline stalled: {c["full_name"]}'
                description = (
                    f'Candidate in {c["current_stage"].replace("_", " ")} '
                    f'for {int(age_hours // 24)} days without progress.'
                )
                due_at = c['updated_at'] + datetime.timedelta(days=14)

            items.append(ActionItem(
                id=self.make_id('recruitment', str(c['id']), action_type),
                action_type=action_type,
                category=ActionCategory.RECRUITMENT,
                priority=priority,
                title=title,
                description=description,
                source_module='recruitment',
                source_record_id=str(c['id']),
                action_url=f'/recruitment/candidates/{c["id"]}/',
                due_date=due_at,
                age_hours=round(age_hours, 1),
                candidate_id=str(c['id']),
                metadata={'stage': c['current_stage']},
            ))

        # Q3: Job postings closing within 3 days
        soon_threshold = today + datetime.timedelta(days=3)
        job_qs = JobPosting.objects.filter(
            company_id=self.company_id,
            status='open',
            is_deleted=False,
            closing_date__isnull=False,
            closing_date__lte=soon_threshold,
            closing_date__gte=today,
        ).values('id', 'title', 'closing_date', 'department')

        for jp in job_qs:
            days_left = (jp['closing_date'] - today).days
            priority = ActionPriority.CRITICAL if days_left == 0 else ActionPriority.HIGH
            due_dt = datetime.datetime.combine(
                jp['closing_date'], datetime.time(23, 59, 59),
                tzinfo=datetime.timezone.utc,
            )
            items.append(ActionItem(
                id=self.make_id('recruitment', str(jp['id']), 'JOB_CLOSING_SOON'),
                action_type='JOB_CLOSING_SOON',
                category=ActionCategory.RECRUITMENT,
                priority=priority,
                title=f'Job closing soon: {jp["title"]}',
                description=f'Posting closes in {days_left} day(s). Extend or close.',
                source_module='recruitment',
                source_record_id=str(jp['id']),
                action_url=f'/recruitment/jobs/{jp["id"]}/',
                due_date=due_dt,
                age_hours=0.0,
                metadata={'department': jp['department'], 'days_left': days_left},
            ))

        return items
