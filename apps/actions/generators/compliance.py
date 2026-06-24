from __future__ import annotations

import datetime
from uuid import UUID

from django.utils import timezone

from apps.hr.models import (
    BackgroundCheck, ComplianceAlert, DisciplinaryRecord, EmployeeCertificate,
)
from ..dataclasses import ActionCategory, ActionItem, ActionPriority
from ..generators.base import BaseActionGenerator
from ..services import register_generator

# Disciplinary kinds that warrant an action
_HIGH_SEVERITY_KINDS = {'pip', 'suspension', 'termination_recommendation'}


@register_generator
class ComplianceActionGenerator(BaseActionGenerator):
    category = ActionCategory.COMPLIANCE.value

    def generate(self) -> list[ActionItem]:
        now = timezone.now()
        today = now.date()
        items: list[ActionItem] = []

        # Q1: Open compliance alerts
        alert_qs = ComplianceAlert.objects.filter(
            company_id=self.company_id,
            status='open',
        ).values('id', 'alert_type', 'employee_id', 'created_at', 'details')

        for alert in alert_qs:
            if self.employee_ids is not None and alert['employee_id'] not in self.employee_ids:
                continue
            age_hours = (now - alert['created_at']).total_seconds() / 3600
            priority = ActionPriority.CRITICAL if alert['alert_type'] == 'below_minimum_wage' else ActionPriority.HIGH
            items.append(ActionItem(
                id=self.make_id('compliance', str(alert['id']), 'COMPLIANCE_ALERT_OPEN'),
                action_type='COMPLIANCE_ALERT_OPEN',
                category=ActionCategory.COMPLIANCE,
                priority=priority,
                title=f'Compliance alert: {alert["alert_type"].replace("_", " ").title()}',
                description=f'Alert open for {int(age_hours // 24)} day(s). Requires acknowledgement.',
                source_module='compliance',
                source_record_id=str(alert['id']),
                action_url=f'/hr/compliance/alerts/{alert["id"]}/',
                age_hours=round(age_hours, 1),
                employee_id=str(alert['employee_id']) if alert['employee_id'] else None,
                metadata={'alert_type': alert['alert_type'], 'details': alert['details']},
            ))

        # Q2: Certificates expiring within their alert_days_before window
        # Use max(30) as the outer bound so one query catches all certs
        outer_threshold = today + datetime.timedelta(days=60)
        cert_qs = EmployeeCertificate.objects.filter(
            company_id=self.company_id,
            is_active=True,
            expiry_date__isnull=False,
            expiry_date__lte=outer_threshold,
            expiry_date__gte=today,
        ).values(
            'id', 'employee_id', 'name', 'expiry_date', 'alert_days_before',
        )

        for cert in cert_qs:
            if self.employee_ids is not None and cert['employee_id'] not in self.employee_ids:
                continue
            days_until = (cert['expiry_date'] - today).days
            # Only generate if within this certificate's own alert window
            if days_until > cert['alert_days_before']:
                continue
            priority = ActionPriority.CRITICAL if days_until <= 7 else ActionPriority.HIGH
            items.append(ActionItem(
                id=self.make_id('compliance', str(cert['id']), 'CERTIFICATE_EXPIRING'),
                action_type='CERTIFICATE_EXPIRING',
                category=ActionCategory.COMPLIANCE,
                priority=priority,
                title=f'Certificate expiring: {cert["name"]}',
                description=f'{cert["name"]} expires {cert["expiry_date"]} ({days_until} day(s) left).',
                source_module='compliance',
                source_record_id=str(cert['id']),
                action_url=f'/hr/certificates/{cert["id"]}/',
                due_date=datetime.datetime.combine(
                    cert['expiry_date'], datetime.time(9, 0),
                    tzinfo=datetime.timezone.utc,
                ),
                age_hours=0.0,
                employee_id=str(cert['employee_id']),
                metadata={
                    'expiry_date': str(cert['expiry_date']),
                    'days_until': days_until,
                    'alert_days_before': cert['alert_days_before'],
                },
            ))

        # Q3: Open/in-progress high-severity disciplinary records
        disc_qs = DisciplinaryRecord.objects.filter(
            company_id=self.company_id,
            status__in=['open', 'in_progress'],
            kind__in=list(_HIGH_SEVERITY_KINDS),
        ).values('id', 'employee_id', 'kind', 'title', 'status', 'created_at', 'starts_on')

        if self.employee_ids is not None:
            disc_qs = disc_qs.filter(employee_id__in=self.employee_ids)

        for disc in disc_qs:
            age_hours = (now - disc['created_at']).total_seconds() / 3600
            priority = (
                ActionPriority.CRITICAL
                if disc['kind'] == 'termination_recommendation'
                else ActionPriority.HIGH
            )
            items.append(ActionItem(
                id=self.make_id('compliance', str(disc['id']), 'DISCIPLINARY_OPEN'),
                action_type='DISCIPLINARY_OPEN',
                category=ActionCategory.COMPLIANCE,
                priority=priority,
                title=f'Disciplinary: {disc["kind"].replace("_", " ").title()}',
                description=f'{disc["title"]} — {disc["status"]}.',
                source_module='compliance',
                source_record_id=str(disc['id']),
                action_url=f'/hr/disciplinary/{disc["id"]}/',
                age_hours=round(age_hours, 1),
                employee_id=str(disc['employee_id']),
                metadata={
                    'kind': disc['kind'],
                    'status': disc['status'],
                    'starts_on': str(disc['starts_on']) if disc['starts_on'] else None,
                },
            ))

        # Q4: Flagged background checks without verdict
        bg_qs = BackgroundCheck.objects.filter(
            company_id=self.company_id,
            is_deleted=False,
            status='flagged',
            verdict__isnull=True,
        ).values(
            'id', 'employee_id', 'candidate_id', 'check_type', 'requested_at', 'flags',
        )

        if self.employee_ids is not None:
            bg_qs = bg_qs.filter(employee_id__in=self.employee_ids)

        for bg in bg_qs:
            age_hours = (now - bg['requested_at']).total_seconds() / 3600
            items.append(ActionItem(
                id=self.make_id('compliance', str(bg['id']), 'BACKGROUND_CHECK_FLAGGED'),
                action_type='BACKGROUND_CHECK_FLAGGED',
                category=ActionCategory.COMPLIANCE,
                priority=ActionPriority.CRITICAL,
                title=f'Background check flagged: {bg["check_type"].replace("_", " ").title()}',
                description=f'Check flagged {int(age_hours // 24)} day(s) ago — no verdict recorded.',
                source_module='compliance',
                source_record_id=str(bg['id']),
                action_url=f'/hr/background-checks/{bg["id"]}/',
                age_hours=round(age_hours, 1),
                employee_id=str(bg['employee_id']) if bg['employee_id'] else None,
                candidate_id=str(bg['candidate_id']) if bg['candidate_id'] else None,
                metadata={
                    'check_type': bg['check_type'],
                    'flags': bg['flags'],
                },
            ))

        return items
