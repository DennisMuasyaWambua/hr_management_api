"""
HR Operations Dashboard — single aggregate endpoint.

Reads across all existing models in one request so the HR admin dashboard
can render its summary cards without making 6+ separate API calls.

No new models. No migrations. Read-only. Company-scoped.
"""
import datetime

from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.models import ServiceAuditLog
from apps.core.permissions import request_company_id

from .models import (
    ComplianceAlert,
    EmployeeCertificate,
    EmployeeExit,
    EmployeeOnboardingDocument,
    LeaveRequest,
)


class DashboardSummaryView(APIView):
    """
    GET /api/dashboard/summary/

    Returns a snapshot of every major HR domain for the requesting company.
    Accessible to any authenticated user; data is scoped to company_id from
    the X-Company-Id header (same convention as the rest of this codebase).

    Sections:
      workforce   — headcount, new hires, pending exits
      attendance  — present/absent today, open violations
      leave       — pending requests, on-leave count
      payroll     — current run status, approval progress
      compliance  — open alerts, expiring certs, missing docs
      recruitment — open positions, active candidates, scheduled interviews
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.attendance.models import AttendanceEvent, GeofenceViolation
        from apps.payroll.models import EmployeeProfile, PayrollRun
        from apps.recruitment.models import Candidate, JobPosting

        company_id = request_company_id(request)
        today = timezone.localdate()
        thirty_days_ago = today - datetime.timedelta(days=30)

        # ── Workforce ──────────────────────────────────────────────────────
        employees = EmployeeProfile.objects.filter(
            is_deleted=False, company_id=company_id
        )
        active_qs = employees.filter(employment_status='active')

        workforce = {
            'total_employees': employees.count(),
            'active_employees': active_qs.count(),
            'new_hires_30d': active_qs.filter(
                start_date__gte=thirty_days_ago
            ).count(),
            'pending_exits': EmployeeExit.objects.filter(
                company_id=company_id,
                status__in=['initiated', 'clearance', 'final_dues'],
            ).count(),
        }

        # ── Attendance ─────────────────────────────────────────────────────
        headcount = workforce['active_employees']
        checked_in_today = (
            AttendanceEvent.objects.filter(
                company_id=company_id,
                event_type='check_in',
                time__date=today,
            )
            .values('employee_id')
            .distinct()
            .count()
        )
        open_violations = GeofenceViolation.objects.filter(
            company_id=company_id, ended_at__isnull=True
        ).count()

        attendance = {
            'date': str(today),
            'headcount': headcount,
            'checked_in': checked_in_today,
            'rate_pct': (
                round(100 * checked_in_today / headcount, 1) if headcount else 0.0
            ),
            'open_violations': open_violations,
        }

        # ── Leave ──────────────────────────────────────────────────────────
        on_leave_today = LeaveRequest.objects.filter(
            company_id=company_id,
            status='approved',
            start_date__lte=today,
            end_date__gte=today,
        ).count()

        leave = {
            'pending_requests': LeaveRequest.objects.filter(
                company_id=company_id, status='pending'
            ).count(),
            'on_leave_today': on_leave_today,
        }

        # ── Payroll ────────────────────────────────────────────────────────
        current_run = (
            PayrollRun.objects.filter(company_id=company_id, is_deleted=False)
            .exclude(status='paid')
            .order_by('-created_at')
            .first()
        )
        payroll = self._payroll_section(current_run)

        # ── Compliance ─────────────────────────────────────────────────────
        expiring_window = today + datetime.timedelta(days=30)
        compliance = {
            'open_alerts': ComplianceAlert.objects.filter(
                company_id=company_id, status='open'
            ).count(),
            'expiring_certs_30d': EmployeeCertificate.objects.filter(
                company_id=company_id,
                is_active=True,
                expiry_date__gte=today,
                expiry_date__lte=expiring_window,
            ).count(),
            'missing_onboarding_docs': EmployeeOnboardingDocument.objects.filter(
                company_id=company_id, status='missing'
            ).count(),
        }

        # ── Recruitment ────────────────────────────────────────────────────
        active_candidate_stages = [
            'screened', 'interview_l1', 'interview_l2', 'offer_sent'
        ]
        hired_30d = Candidate.objects.filter(
            company_id=company_id,
            is_deleted=False,
            current_stage='hired',
            updated_at__date__gte=thirty_days_ago,
        ).count()

        # Interview count — graceful if Interview model not yet migrated
        interviews_scheduled = self._interviews_scheduled(company_id, today)

        recruitment = {
            'open_positions': JobPosting.objects.filter(
                company_id=company_id, status='open', is_deleted=False
            ).count(),
            'active_candidates': Candidate.objects.filter(
                company_id=company_id,
                is_deleted=False,
                current_stage__in=active_candidate_stages,
            ).count(),
            'interviews_scheduled': interviews_scheduled,
            'hired_30d': hired_30d,
        }

        return Response({
            'workforce': workforce,
            'attendance': attendance,
            'leave': leave,
            'payroll': payroll,
            'compliance': compliance,
            'recruitment': recruitment,
        })

    # ── Helpers ────────────────────────────────────────────────────────────

    @staticmethod
    def _payroll_section(run):
        if run is None:
            return {
                'current_run_status': None,
                'current_run_period': None,
                'approvals_given': 0,
                'approvals_required': 0,
                'total_net_current': None,
            }

        approvals_given = 0
        approvals_required = 0
        if run.status == 'pending_approval':
            try:
                from apps.payroll.approval_models import (
                    ApproverConfig, PayrollApproval,
                )
                approvals_given = PayrollApproval.objects.filter(
                    payroll_run_id=run.id, decision='approved'
                ).count()
                cfg = ApproverConfig.objects.filter(
                    company_id=run.company_id, is_active=True
                ).first()
                approvals_required = cfg.required_approvals if cfg else 0
            except Exception:
                pass

        return {
            'current_run_status': run.status,
            'current_run_period': run.period_display,
            'approvals_given': approvals_given,
            'approvals_required': approvals_required,
            'total_net_current': (
                float(run.total_net) if run.total_net else None
            ),
        }

    @staticmethod
    def _interviews_scheduled(company_id, today):
        try:
            from apps.recruitment.models import Interview
            return Interview.objects.filter(
                company_id=company_id,
                status='scheduled',
                scheduled_at__date__gte=today,
            ).count()
        except Exception:
            return 0
