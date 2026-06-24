"""
Fire time-based workflow triggers.

Supported triggers:
  contract_expiring — EmployeeProfile records with end_date within N days
  performance_review_due — placeholder (no PerformanceReview model yet)

Run: python manage.py run_workflow_scheduled_triggers
"""
from datetime import date, timedelta

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Fire scheduled workflow triggers (contract_expiring, performance_review_due)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days-ahead', type=int, default=30,
            help='Days ahead to look for expiring contracts (default 30)',
        )

    def handle(self, *args, **options):
        days_ahead = options['days_ahead']
        today = date.today()
        threshold = today + timedelta(days=days_ahead)

        self._fire_contract_expiring(today, threshold)

    def _fire_contract_expiring(self, today: date, threshold: date) -> None:
        from apps.payroll.models import EmployeeProfile
        from apps.workflows.engine import WorkflowEngine

        expiring = EmployeeProfile.objects.filter(
            end_date__isnull=False,
            end_date__lte=threshold,
            end_date__gte=today,
            is_deleted=False,
        )

        total_fired = 0
        for emp in expiring:
            company_id = emp.company_id
            if not company_id:
                continue
            days_until = (emp.end_date - today).days
            context = {
                'id': str(emp.id),
                'employee_id': str(emp.id),
                'employee_number': emp.employee_number,
                'job_title': emp.job_title,
                'contract_end_date': str(emp.end_date),
                'days_until_expiry': str(days_until),
                'company_id': str(company_id),
            }
            executions = WorkflowEngine.fire('contract_expiring', context, company_id)
            total_fired += len(executions)

        self.stdout.write(
            self.style.SUCCESS(
                f'contract_expiring: checked {expiring.count()} employee(s), '
                f'fired {total_fired} workflow execution(s).'
            )
        )
