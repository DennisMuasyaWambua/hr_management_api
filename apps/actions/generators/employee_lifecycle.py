from __future__ import annotations

import datetime
from uuid import UUID

from django.utils import timezone

from ..dataclasses import ActionCategory, ActionItem, ActionPriority
from ..generators.base import BaseActionGenerator
from ..services import register_generator

_CONTRACT_EXPIRY_DAYS = 30
_PROBATION_DAYS = 90
_PROBATION_WINDOW_DAYS = 7   # flag in ±7 day window around day 90
_GEOFENCE_GRACE_HOURS = 24


@register_generator
class EmployeeLifecycleActionGenerator(BaseActionGenerator):
    category = ActionCategory.EMPLOYEE_LIFECYCLE.value

    def generate(self) -> list[ActionItem]:
        from apps.attendance.models import GeofenceViolation
        from apps.hr.models import KpiAssignment
        from apps.payroll.models import EmployeeProfile

        now = timezone.now()
        today = now.date()
        items: list[ActionItem] = []

        # Q1: All active employees — bucket into contract/probation/statutory in one pass
        expiry_threshold = today + datetime.timedelta(days=_CONTRACT_EXPIRY_DAYS)
        probation_early = today - datetime.timedelta(days=_PROBATION_WINDOW_DAYS)
        probation_late = today + datetime.timedelta(days=_PROBATION_WINDOW_DAYS)
        probation_from = probation_early - datetime.timedelta(days=_PROBATION_DAYS)
        probation_to = probation_late - datetime.timedelta(days=_PROBATION_DAYS)

        employee_qs = EmployeeProfile.objects.filter(
            company_id=self.company_id,
            is_deleted=False,
            employment_status='active',
        ).values(
            'id', 'employee_number', 'job_title', 'start_date', 'end_date',
            'nssf_number', 'nhif_number', 'kra_pin',
        )

        if self.employee_ids is not None:
            employee_qs = employee_qs.filter(id__in=self.employee_ids)

        for emp in employee_qs:
            emp_id = str(emp['id'])

            # CONTRACT_EXPIRING
            if emp['end_date'] and emp['end_date'] <= expiry_threshold:
                days_left = (emp['end_date'] - today).days
                priority = ActionPriority.CRITICAL if days_left <= 7 else ActionPriority.HIGH
                items.append(ActionItem(
                    id=self.make_id('employee_lifecycle', emp_id, 'CONTRACT_EXPIRING'),
                    action_type='CONTRACT_EXPIRING',
                    category=ActionCategory.EMPLOYEE_LIFECYCLE,
                    priority=priority,
                    title=f'Contract expiring: {emp["job_title"]}',
                    description=f'Contract ends {emp["end_date"]} ({days_left} day(s) remaining).',
                    source_module='employee_lifecycle',
                    source_record_id=emp_id,
                    action_url=f'/hr/employees/{emp_id}/',
                    due_date=datetime.datetime.combine(
                        emp['end_date'], datetime.time(9, 0),
                        tzinfo=datetime.timezone.utc,
                    ),
                    age_hours=0.0,
                    employee_id=emp_id,
                    metadata={
                        'end_date': str(emp['end_date']),
                        'days_left': days_left,
                        'employee_number': emp['employee_number'],
                    },
                ))

            # PROBATION_REVIEW_DUE
            if emp['start_date'] and probation_from <= emp['start_date'] <= probation_to:
                review_date = emp['start_date'] + datetime.timedelta(days=_PROBATION_DAYS)
                days_to_review = (review_date - today).days
                items.append(ActionItem(
                    id=self.make_id('employee_lifecycle', emp_id, 'PROBATION_REVIEW_DUE'),
                    action_type='PROBATION_REVIEW_DUE',
                    category=ActionCategory.EMPLOYEE_LIFECYCLE,
                    priority=ActionPriority.HIGH,
                    title=f'Probation review due: {emp["job_title"]}',
                    description=(
                        f'90-day probation review '
                        f'{"in " + str(abs(days_to_review)) + " days" if days_to_review > 0 else "overdue by " + str(abs(days_to_review)) + " days"}.'
                    ),
                    source_module='employee_lifecycle',
                    source_record_id=emp_id,
                    action_url=f'/hr/employees/{emp_id}/',
                    due_date=datetime.datetime.combine(
                        review_date, datetime.time(9, 0),
                        tzinfo=datetime.timezone.utc,
                    ),
                    age_hours=max(0.0, -days_to_review * 24.0),
                    employee_id=emp_id,
                    metadata={
                        'start_date': str(emp['start_date']),
                        'review_date': str(review_date),
                        'employee_number': emp['employee_number'],
                    },
                ))

            # STATUTORY_NUMBER_MISSING
            missing = [
                label for field_name, label in [
                    ('nssf_number', 'NSSF'), ('nhif_number', 'NHIF'), ('kra_pin', 'KRA PIN'),
                ]
                if not emp[field_name]
            ]
            if missing:
                items.append(ActionItem(
                    id=self.make_id('employee_lifecycle', emp_id, 'STATUTORY_NUMBER_MISSING'),
                    action_type='STATUTORY_NUMBER_MISSING',
                    category=ActionCategory.EMPLOYEE_LIFECYCLE,
                    priority=ActionPriority.MEDIUM,
                    title='Statutory numbers missing',
                    description=f'Missing: {", ".join(missing)}.',
                    source_module='employee_lifecycle',
                    source_record_id=emp_id,
                    action_url=f'/hr/employees/{emp_id}/',
                    age_hours=0.0,
                    employee_id=emp_id,
                    metadata={
                        'missing_fields': missing,
                        'employee_number': emp['employee_number'],
                    },
                ))

        # Q2: Overdue KPI submissions for current/past periods
        current_quarter = (today.month - 1) // 3 + 1
        kpi_qs = KpiAssignment.objects.filter(
            company_id=self.company_id,
            is_deleted=False,
            submitted_at__isnull=True,
        ).filter(
            period_year__lt=today.year,
        ) | KpiAssignment.objects.filter(
            company_id=self.company_id,
            is_deleted=False,
            submitted_at__isnull=True,
            period_year=today.year,
            period_quarter__lte=current_quarter,
        )

        if self.employee_ids is not None:
            kpi_qs = kpi_qs.filter(employee_id__in=self.employee_ids)

        for kpi in kpi_qs.values('id', 'employee_id', 'period_quarter', 'period_year', 'created_at'):
            age_hours = (now - kpi['created_at']).total_seconds() / 3600
            items.append(ActionItem(
                id=self.make_id('employee_lifecycle', str(kpi['id']), 'PERFORMANCE_REVIEW_OVERDUE'),
                action_type='PERFORMANCE_REVIEW_OVERDUE',
                category=ActionCategory.EMPLOYEE_LIFECYCLE,
                priority=ActionPriority.MEDIUM,
                title='Performance review overdue',
                description=(
                    f'Q{kpi["period_quarter"]} {kpi["period_year"]} KPI not yet submitted.'
                ),
                source_module='employee_lifecycle',
                source_record_id=str(kpi['id']),
                action_url=f'/hr/kpi/{kpi["id"]}/',
                age_hours=round(age_hours, 1),
                employee_id=str(kpi['employee_id']),
                metadata={
                    'period_quarter': kpi['period_quarter'],
                    'period_year': kpi['period_year'],
                },
            ))

        # Q3: Open geofence violations > 24 hours without response
        geo_threshold = now - datetime.timedelta(hours=_GEOFENCE_GRACE_HOURS)
        geo_qs = GeofenceViolation.objects.filter(
            company_id=self.company_id,
            status='open',
            started_at__lt=geo_threshold,
        ).values('id', 'employee_id', 'started_at', 'distance_m')

        if self.employee_ids is not None:
            geo_qs = geo_qs.filter(employee_id__in=self.employee_ids)

        for gv in geo_qs:
            age_hours = (now - gv['started_at']).total_seconds() / 3600
            items.append(ActionItem(
                id=self.make_id('employee_lifecycle', str(gv['id']), 'GEOFENCE_VIOLATION_OPEN'),
                action_type='GEOFENCE_VIOLATION_OPEN',
                category=ActionCategory.EMPLOYEE_LIFECYCLE,
                priority=ActionPriority.MEDIUM,
                title='Geofence violation unresolved',
                description=f'Violation open {int(age_hours)}h — no reason submitted.',
                source_module='employee_lifecycle',
                source_record_id=str(gv['id']),
                action_url=f'/attendance/geofence-violations/{gv["id"]}/',
                age_hours=round(age_hours, 1),
                employee_id=str(gv['employee_id']),
                metadata={'distance_m': gv['distance_m']},
            ))

        return items
