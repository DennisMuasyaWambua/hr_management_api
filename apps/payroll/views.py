from rest_framework import viewsets, status, views, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.authtoken.models import Token
from django.contrib.auth import authenticate, get_user_model
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from decimal import Decimal
import logging

from apps.core.models import ServiceAuditLog
from apps.core.permissions import request_user_id, request_company_id


def _get_tenant_id(request):
    """Resolve tenant_id safely for both ServiceUser and plain auth.User.

    Token-authenticated requests use Django's auth.User which has no tenant_id.
    Fall back to the company's tenant_id when it's missing from the user object.
    """
    user = request.user
    if hasattr(user, 'tenant_id') and user.tenant_id:
        return user.tenant_id
    company_id = request_company_id(request)
    if company_id:
        try:
            company = Company.objects.only('tenant_id').get(id=company_id, is_deleted=False)
            return company.tenant_id
        except Company.DoesNotExist:
            pass
    return None

from .models import PayrollRun, PayrollRecord, PaymentBatch, EmployeeProfile, Company
from .serializers import (
    PayrollRunListSerializer, PayrollRunDetailSerializer,
    PayrollRunCreateSerializer, PayrollRecordSerializer,
    DisbursePayrollSerializer, PaymentBatchSerializer,
    EmployeePaymentSerializer, EmployeePayrollStatusSerializer,
    DepartmentPaymentStatusSerializer, PaymentHistoryRecordSerializer,
    CompanySerializer, EmployeeProfileListSerializer, MyPayslipSerializer,
)
from .services.tax_calculator import KenyanTaxCalculator
from .services.pesapal import PesaPalService
from .services.intasend import IntaSendService
from .tasks import process_payment_batch, process_ipn_callback

User = get_user_model()
logger = logging.getLogger(__name__)

# Authority ranking (lower = more authority) used to surface a user's highest
# role at login. A user's AppUser.role is compared against any RBAC role
# assignments so that e.g. an hr_admin granted the company_admin RBAC role logs
# in as company_admin (full dashboard access).
_ROLE_RANK = {
    'super_admin': 0, 'company_admin': 1,
    'hr_admin': 2, 'hr': 2, 'internal_hr': 2, 'deployed_hr': 2,
    'manager': 3, 'internal_manager': 3, 'deployed_manager': 3,
    'employee': 4, 'white_collar_employee': 4, 'blue_collar_employee': 4,
}


def _effective_role(profile):
    """Highest-authority role for a user: the better of their AppUser.role and
    any assigned RBAC role."""
    if profile is None:
        return 'super_admin'  # legacy: tokenless/no-profile users
    best = getattr(profile, 'role', None) or 'employee'
    best_rank = _ROLE_RANK.get(best, 5)
    try:
        from apps.core.models import UserRoleAssignment
        for a in UserRoleAssignment.objects.filter(
                user_id=profile.id).select_related('role'):
            slug = a.role.slug
            if _ROLE_RANK.get(slug, 5) < best_rank:
                best, best_rank = slug, _ROLE_RANK.get(slug, 5)
    except Exception:  # noqa: BLE001 — never block login on RBAC lookup
        logger.exception('effective-role lookup failed for %s', profile.id)
    return best


class AuthLoginView(views.APIView):
    """
    Email + password login — returns DRF token and basic user info.
    Used by the Next.js dashboard to replace Supabase auth.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get('email', '').strip().lower()
        password = request.data.get('password', '')
        if not email or not password:
            return Response({'error': 'email and password are required'}, status=400)

        # Look up the user by email or username. Legacy seeding (the
        # create_admin release command vs. dashboard-created users) can leave
        # more than one auth.User sharing an email, so never use .get() here —
        # it would raise MultipleObjectsReturned and 500 the login. Gather all
        # candidates and pick the one whose password matches, preferring one
        # that has a linked AppUser profile (hr_profile).
        candidates = list(User.objects.filter(email=email))
        if not candidates:
            candidates = list(User.objects.filter(username=email))
        if not candidates:
            return Response({'error': 'Invalid credentials'}, status=401)

        user = None
        for candidate in candidates:
            if candidate.check_password(password):
                user = candidate
                # A candidate with a profile is the best match; stop searching.
                if getattr(candidate, 'hr_profile', None) is not None:
                    break
        if user is None:
            return Response({'error': 'Invalid credentials'}, status=401)

        if not user.is_active:
            return Response({'error': 'Account is inactive'}, status=403)

        token, _ = Token.objects.get_or_create(user=user)

        profile = getattr(user, 'hr_profile', None)
        # X-User-Id must be a UUID (apps.core.permissions docstring: "Supabase
        # user UUID"; apps.core.models.ServiceAuditLog.actor_user_id is a
        # UUIDField) — Django's auth.User.id is an int, so use the AppUser
        # ("hr_profile") UUID when one exists. Falls back to the int id for
        # legacy users with no profile yet; that's only safe as long as
        # nothing on their path needs a real UUID (audit logging does).
        user_id = str(profile.id) if profile else str(user.id)
        return Response({
            'token': token.key,
            'user_id': user_id,
            'email': user.email,
            'username': user.username,
            'full_name': getattr(profile, 'full_name', '') or user.get_full_name() or user.username,
            'role': _effective_role(profile),
            'company_id': str(getattr(profile, 'company_id', '') or ''),
            'tenant_id': str(getattr(profile, 'tenant_id', '') or ''),
            'employee_id': str(getattr(profile, 'employee_id', '') or ''),
        })


class MeView(views.APIView):
    """Returns the current authenticated user's info."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        profile = getattr(user, 'hr_profile', None)

        # Pull extra fields from EmployeeProfile keyed by the Supabase UUID
        # forwarded in X-User-Id by the Next.js proxy.
        face_descriptor = None
        worker_class = 'white_collar'
        employee_id = str(getattr(profile, 'employee_id', '') or '')
        supabase_uid = request_user_id(request)
        if supabase_uid:
            ep = EmployeeProfile.objects.filter(
                user_id=supabase_uid, is_deleted=False
            ).values('face_descriptor', 'worker_class', 'id').first()
            if ep:
                face_descriptor = ep['face_descriptor']
                worker_class = ep['worker_class'] or 'white_collar'
                employee_id = str(ep['id'])

        return Response({
            'user_id': str(user.id),
            'email': user.email,
            'username': user.username,
            'full_name': getattr(profile, 'full_name', '') or user.get_full_name() or user.username,
            'role': getattr(profile, 'role', 'super_admin'),
            'company_id': str(getattr(profile, 'company_id', '') or ''),
            'employee_id': employee_id,
            'worker_class': worker_class,
            'face_descriptor': face_descriptor,
        })


class CompanyViewSet(viewsets.ModelViewSet):
    """CRUD for companies — replaces Supabase direct queries."""
    serializer_class = CompanySerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'contact_email', 'industry']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']

    def get_queryset(self):
        from apps.core.permissions import CROSS_COMPANY_ROLES, request_role
        qs = Company.objects.filter(is_deleted=False, is_active=True)
        # Explicit filter always wins (company switcher, direct lookup).
        explicit = (
            self.request.query_params.get('companyId') or
            self.request.query_params.get('company_id')
        )
        if explicit:
            return qs.filter(id=explicit)
        # Non-cross-company roles (hr, manager, employee) see only their company.
        role = request_role(self.request)
        if role and role not in CROSS_COMPANY_ROLES:
            session_company = request_company_id(self.request)
            if session_company:
                return qs.filter(id=session_company)
        return qs

    def perform_create(self, serializer):
        serializer.save()

    def perform_update(self, serializer):
        serializer.save()


class EmployeeProfileViewSet(viewsets.ModelViewSet):
    """Full employee-profile CRUD — replaces Supabase direct queries."""
    serializer_class = EmployeeProfileListSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['employee_number', 'job_title', 'department']
    ordering_fields = ['created_at', 'employee_number']
    ordering = ['-created_at']

    def get_queryset(self):
        qs = EmployeeProfile.objects.filter(is_deleted=False)
        company_id = (
            self.request.query_params.get('companyId') or
            self.request.query_params.get('company_id')
        )
        if company_id:
            qs = qs.filter(company_id=company_id)
        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(employment_status=status_filter)
        dept = self.request.query_params.get('department')
        if dept:
            qs = qs.filter(department=dept)
        emp_type = self.request.query_params.get('employmentType')
        if emp_type:
            qs = qs.filter(employment_type=emp_type)
        # Contract expiry filters used by the dashboard summary
        p = self.request.query_params
        if p.get('end_date_after'):
            qs = qs.filter(end_date__gte=p['end_date_after'])
        if p.get('end_date_before'):
            qs = qs.filter(end_date__lte=p['end_date_before'])
        if p.get('employment_status'):
            qs = qs.filter(employment_status=p['employment_status'])
        # Deployed HR/Managers only see their assigned employees; internal roles
        # and company_admin are scoped to their company. (super_admin: all)
        from apps.core.permissions import scope_employee_queryset
        qs = scope_employee_queryset(qs, self.request)
        return qs

    def create(self, request, *args, **kwargs):
        """Create the employee profile, then persist any onboarding Benefits
        (A4) as EmployeeAllowance rows so they immediately feed into payroll
        computation (taxable benefits raise the PAYE base; all benefits raise
        gross/net). Benefits are sent as `benefits: [{name, type, value,
        value_is_percent, recurring}]` alongside the profile fields."""
        benefits = request.data.get('benefits') or []
        response = super().create(request, *args, **kwargs)

        if response.status_code in (200, 201) and benefits:
            from apps.hr.models import AllowanceType, EmployeeAllowance
            emp_id = response.data.get('id')
            company_id = response.data.get('company_id')
            tenant_id = response.data.get('tenant_id')
            try:
                salary = Decimal(str(response.data.get('salary') or 0))
            except Exception:
                salary = Decimal('0')
            non_taxable_types = {'medical', 'insurance'}
            created_by = request_user_id(request)

            for b in benefits:
                name = (b.get('name') or '').strip()
                if not name:
                    continue
                btype = (b.get('type') or 'other').lower()
                try:
                    raw = Decimal(str(b.get('value') or 0))
                except Exception:
                    raw = Decimal('0')
                if b.get('value_is_percent'):
                    amount = (salary * raw / Decimal('100')).quantize(Decimal('0.01'))
                else:
                    amount = raw
                recurring = b.get('recurring', True)

                atype, _ = AllowanceType.objects.get_or_create(
                    company_id=company_id, name=name,
                    defaults={
                        'tenant_id': tenant_id,
                        'taxable': btype not in non_taxable_types,
                        # A non-recurring benefit is a one-off: model it as a
                        # variable allowance that resets at month end.
                        'is_variable': not recurring,
                    },
                )
                EmployeeAllowance.objects.create(
                    tenant_id=tenant_id, company_id=company_id,
                    employee_id=emp_id, allowance_type=atype,
                    amount=amount, created_by=created_by,
                )

        return response

    @action(detail=True, methods=['post'])
    def terminate(self, request, pk=None):
        """Ends an employee's employment: flips employment_status, sets
        end_date, and opens an EmployeeExit record (apps.hr) so the existing
        clearance/final-dues workflow can pick it up."""
        from apps.hr.models import EmployeeExit

        employee = self.get_object()
        reason = request.data.get('reason', 'terminated')
        kind = {
            'resigned': 'resignation', 'terminated': 'termination',
            'contract_end': 'contract_end', 'redundancy': 'redundancy',
            'misconduct': 'termination',
        }.get(reason, 'termination')
        last_working_date = request.data.get('last_working_date')

        employee.employment_status = 'resigned' if reason == 'resigned' else 'terminated'
        employee.end_date = last_working_date or employee.end_date
        employee.save(update_fields=['employment_status', 'end_date', 'updated_at'])

        exit_record = EmployeeExit.objects.create(
            tenant_id=employee.tenant_id, company_id=employee.company_id,
            employee_id=employee.id, kind=kind,
            reason=request.data.get('details', ''),
            last_working_day=last_working_date,
            initiated_by=request_user_id(request) if request_user_id(request) else None,
        )
        ServiceAuditLog.log('employee.terminated', request=request,
                            object_type='EmployeeProfile', object_id=str(employee.id),
                            company_id=employee.company_id,
                            metadata={'exit_id': str(exit_record.id), 'kind': kind})

        return Response(EmployeeProfileListSerializer(employee).data)

    def perform_create(self, serializer):
        serializer.save()

    def perform_update(self, serializer):
        serializer.save()


class PayrollRunViewSet(viewsets.ModelViewSet):
    """
    Payroll Run management endpoints

    Workflow: draft → calculated → approved → processing → completed
    """
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = PayrollRun.objects.filter(is_deleted=False)
        company_id = request_company_id(self.request)
        if company_id:
            qs = qs.filter(company_id=company_id)
        else:
            tenant_id = _get_tenant_id(self.request)
            if tenant_id:
                qs = qs.filter(tenant_id=tenant_id)
        return qs

    def get_serializer_class(self):
        if self.action == 'list':
            return PayrollRunListSerializer
        if self.action == 'create':
            return PayrollRunCreateSerializer
        return PayrollRunDetailSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        company_id = request_company_id(self.request)
        if company_id:
            context['company_id'] = company_id
        elif hasattr(self.request.user, 'company_id'):
            context['company_id'] = self.request.user.company_id
        return context

    def perform_create(self, serializer):
        tenant_id = _get_tenant_id(self.request)
        company_id = request_company_id(self.request) or (
            self.request.user.company_id if hasattr(self.request.user, 'company_id') else None
        )
        serializer.save(
            tenant_id=tenant_id,
            company_id=company_id,
            run_by=self.request.user.id,
            status='draft'
        )

    @action(detail=True, methods=['post'])
    def calculate(self, request, pk=None):
        """
        Calculate payroll for all active employees.
        Generates PayrollRecord for each employee with tax calculations.
        """
        payroll_run = self.get_object()

        if payroll_run.status != 'draft':
            return Response(
                {'error': 'Can only calculate draft payroll runs'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get active employees — scoped to the selected employee_ids when the
        # caller provides them, so a run (and its approval email) covers only
        # the chosen employees rather than the whole company.
        employees = EmployeeProfile.objects.filter(
            company_id=payroll_run.company_id,
            employment_status='active',
            is_deleted=False
        )
        selected_ids = request.data.get('employee_ids') or []
        if selected_ids:
            employees = employees.filter(id__in=selected_ids)
            if not employees.exists():
                return Response(
                    {'error': 'None of the selected employees are active in this company'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        calculator = KenyanTaxCalculator()

        with transaction.atomic():
            # Clear existing records
            PayrollRecord.objects.filter(payroll_run=payroll_run).delete()

            records = []
            totals = {
                'gross': Decimal('0'),
                'deductions': Decimal('0'),
                'net': Decimal('0'),
            }

            # Active allowances/deductions for this payroll period. Allowances
            # default to a single month (effective_to set at creation) and must
            # be renewed to carry over; we honour whatever window is stored.
            import datetime as _dt
            from apps.hr.models import EmployeeAllowance, EmployeeDeduction
            _year, _month = payroll_run.period_year, payroll_run.period_month
            _first = _dt.date(_year, _month, 1)
            _emp_ids = [e.id for e in employees]
            allow_by_emp, ded_by_emp = {}, {}
            for a in EmployeeAllowance.objects.filter(
                    employee_id__in=_emp_ids, is_active=True
            ).select_related('allowance_type'):
                if a.active_for(_year, _month):
                    allow_by_emp.setdefault(str(a.employee_id), []).append(a)
            for d in EmployeeDeduction.objects.filter(
                    employee_id__in=_emp_ids, is_active=True):
                if (d.effective_from <= _first.replace(day=28) and
                        (d.effective_to is None or d.effective_to >= _first)):
                    ded_by_emp.setdefault(str(d.employee_id), []).append(d)

            for employee in employees:
                emp_allows = allow_by_emp.get(str(employee.id), [])
                taxable_allow = sum((a.amount for a in emp_allows
                                     if a.allowance_type.taxable), Decimal('0'))
                nontax_allow = sum((a.amount for a in emp_allows
                                    if not a.allowance_type.taxable), Decimal('0'))
                extra_deductions = sum((d.amount for d in
                                        ded_by_emp.get(str(employee.id), [])),
                                       Decimal('0'))

                # Taxable allowances are part of the PAYE/statutory base.
                taxable_gross = employee.salary + taxable_allow
                calcs = calculator.calculate_all(
                    gross_pay=taxable_gross, helb_deduction=Decimal('0'))

                paye = calcs['paye']
                nssf = calcs['nssf_employee']
                nhif = calcs['nhif']
                helb = calcs['helb']
                statutory = paye + nssf + nhif + helb
                other_deductions = extra_deductions
                gross_salary = employee.salary + taxable_allow + nontax_allow
                total_deductions = statutory + other_deductions
                net_salary = gross_salary - total_deductions

                record = PayrollRecord(
                    tenant_id=payroll_run.tenant_id,
                    payroll_run=payroll_run,
                    employee=employee,
                    gross_salary=gross_salary,
                    paye=paye,
                    nssf=nssf,
                    nhif=nhif,
                    helb=helb,
                    other_deductions=other_deductions,
                    net_salary=net_salary,
                    payment_method=employee.payment_method,
                    payment_status='pending'
                )
                records.append(record)

                # Update totals
                totals['gross'] += gross_salary
                totals['deductions'] += total_deductions
                totals['net'] += net_salary

            PayrollRecord.objects.bulk_create(records)

            # Update payroll run totals
            payroll_run.status = 'calculated'
            payroll_run.total_gross = totals['gross']
            payroll_run.total_deductions = totals['deductions']
            payroll_run.total_net = totals['net']
            payroll_run.save()

        return Response(PayrollRunDetailSerializer(payroll_run).data)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """Approve payroll run for disbursement"""
        payroll_run = self.get_object()

        if payroll_run.status != 'calculated':
            return Response(
                {'error': 'Can only approve calculated payroll runs'},
                status=status.HTTP_400_BAD_REQUEST
            )

        payroll_run.status = 'approved'
        payroll_run.save()

        return Response(PayrollRunDetailSerializer(payroll_run).data)

    @action(detail=True, methods=['post'])
    def disburse(self, request, pk=None):
        """
        Trigger salary disbursement.
        Creates payment batches and queues for async processing.
        """
        payroll_run = self.get_object()

        if payroll_run.status not in ['approved', 'processing']:
            return Response(
                {'error': 'Payroll must be approved before disbursement'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Sign-then-disburse policy: even an 'approved' run cannot be paid out
        # until the employer has e-signed it via DocuSeal. This closes the hole
        # where the plain `approve` action sets status without any signature.
        if getattr(settings, 'PAYROLL_REQUIRE_SIGNATURE', True):
            from .approval_models import PayrollApproval, PayrollDocument
            signed = (
                PayrollApproval.objects.filter(
                    payroll_run_id=payroll_run.id, decision='approved',
                    via='docuseal').exists()
                or PayrollDocument.objects.filter(
                    payroll_run_id=payroll_run.id, is_signed=True).exists()
            )
            if not signed:
                return Response(
                    {'error': 'Payroll must be signed by the employer via DocuSeal '
                              'before disbursement. Send it for signing first.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        serializer = DisbursePayrollSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Get pending records
        records = payroll_run.records.filter(payment_status='pending')

        if serializer.validated_data.get('record_ids'):
            records = records.filter(id__in=serializer.validated_data['record_ids'])

        if serializer.validated_data.get('payment_methods'):
            records = records.filter(
                payment_method__in=serializer.validated_data['payment_methods']
            )

        if not records.exists():
            return Response(
                {'error': 'No pending payments found'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # ------------------------------------------------------------------
        # A2 — Proof-of-disbursement payout. Rather than paying every employee
        # their full net salary, fire a single fixed M-Pesa B2C of KES 10 to
        # the configured demo number to prove the live disbursement rail is
        # wired and signed-off. Controlled by DISBURSE_TEST_PAYOUT (default
        # True); set False to fall through to real per-employee batch payments.
        # ------------------------------------------------------------------
        if getattr(settings, 'DISBURSE_TEST_PAYOUT', True):
            test_phone = getattr(settings, 'DISBURSE_TEST_PHONE', '+254720523299')
            test_amount = Decimal(str(getattr(settings, 'DISBURSE_TEST_AMOUNT', 10)))
            reference = f'SL-DISB-{payroll_run.id.hex[:8]}-{int(timezone.now().timestamp())}'

            intasend = IntaSendService()
            result = intasend.send_mpesa(
                phone=test_phone,
                amount=float(test_amount),
                reference=reference,
                name='Sheer Logic Payroll',
                narrative=f'Payroll {payroll_run.period_display} disbursement',
            )

            # Audit the attempt regardless of outcome (A2: timestamp, actor,
            # status, response are captured by ServiceAuditLog).
            ServiceAuditLog.log(
                'payroll.disbursed', request=request,
                tenant_id=payroll_run.tenant_id,
                company_id=payroll_run.company_id,
                object_type='payroll_run', object_id=str(payroll_run.id),
                metadata={
                    'mode': 'fixed_proof_payout',
                    'phone': test_phone,
                    'amount': float(test_amount),
                    'reference': reference,
                    'record_count': records.count(),
                    'success': bool(result.get('success')),
                    'tracking_id': result.get('tracking_id'),
                    'provider_status': result.get('status'),
                    'error': result.get('error'),
                },
            )

            if not result.get('success'):
                return Response(
                    {'error': result.get('error', 'M-Pesa disbursement failed'),
                     'reference': reference},
                    status=status.HTTP_400_BAD_REQUEST
                )

            now = timezone.now()
            batch = PaymentBatch.objects.create(
                tenant_id=payroll_run.tenant_id,
                payroll_run=payroll_run,
                payment_method='mpesa',
                status='completed',
                total_amount=test_amount,
                successful_amount=test_amount,
                record_count=records.count(),
                successful_count=records.count(),
            )
            records.update(
                payment_status='paid', payment_reference=reference, paid_at=now
            )
            payroll_run.status = 'paid'
            payroll_run.completed_at = now
            payroll_run.save()

            return Response({
                'message': f'Disbursement initiated: KES {test_amount} sent to {test_phone}',
                'reference': reference,
                'tracking_id': result.get('tracking_id'),
                'batches': PaymentBatchSerializer([batch], many=True).data,
            })

        # Group by payment method and create batches
        batches = []
        for method in ['bank', 'mpesa', 'airtel']:
            method_records = records.filter(payment_method=method)
            if method_records.exists():
                batch = PaymentBatch.objects.create(
                    tenant_id=payroll_run.tenant_id,
                    payroll_run=payroll_run,
                    payment_method=method,
                    total_amount=sum(r.net_salary for r in method_records),
                    record_count=method_records.count(),
                    status='pending'
                )
                batches.append(batch)

                # Process payments - use sync mode for demo, async for production
                demo_mode = getattr(settings, 'PAYMENT_DEMO_MODE', False)
                if demo_mode:
                    # Process synchronously for demo (no Celery needed)
                    process_payment_batch(str(batch.id))
                else:
                    # Queue async processing — but never let a missing/broken
                    # Celery broker block a real disbursement: fall back to
                    # running the batch synchronously in-request.
                    try:
                        process_payment_batch.delay(str(batch.id))
                    except Exception:
                        logger.warning('Celery unavailable; processing payment '
                                       'batch %s synchronously', batch.id, exc_info=True)
                        process_payment_batch(str(batch.id))

        # Update payroll run status
        payroll_run.status = 'processing'
        payroll_run.save()

        return Response({
            'message': f'Disbursement started for {records.count()} payments',
            'batches': PaymentBatchSerializer(batches, many=True).data
        })

    @action(detail=True, methods=['get'])
    def payment_status(self, request, pk=None):
        """Get current payment status for all batches"""
        payroll_run = self.get_object()
        batches = payroll_run.payment_batches.all()

        record_count = payroll_run.records.count()
        summary = {
            'total_records': record_count,
            'pending': payroll_run.records.filter(payment_status='pending').count(),
            'processing': payroll_run.records.filter(payment_status='processing').count(),
            'paid': payroll_run.records.filter(payment_status='paid').count(),
            'failed': payroll_run.records.filter(payment_status='failed').count(),
        }

        return Response({
            'summary': summary,
            'batches': PaymentBatchSerializer(batches, many=True).data
        })

    @action(detail=True, methods=['post'])
    def retry_failed(self, request, pk=None):
        """Retry failed payments"""
        payroll_run = self.get_object()

        failed_records = payroll_run.records.filter(payment_status='failed')

        if not failed_records.exists():
            return Response({'message': 'No failed payments to retry'})

        # Reset to pending
        failed_records.update(payment_status='pending')

        # Re-trigger disbursement for these records
        return self.disburse(request, pk)


class EmployeePaymentViewSet(viewsets.GenericViewSet):
    """Employee payment method management"""
    permission_classes = [IsAuthenticated]
    serializer_class = EmployeePaymentSerializer

    def get_queryset(self):
        # NOTE: was filtering by tenant_id, but ServiceKeyAuthentication
        # only ever populates tenant_id/company_id from the same
        # `company_id` request param — and EmployeeProfile.tenant_id is a
        # distinct field from company_id (see TenantStamped), so the old
        # filter silently matched nothing whenever they differ. company_id
        # is what every other CompanyScopedViewSet in this codebase filters
        # on; match that convention.
        company_id = request_company_id(self.request)
        qs = EmployeeProfile.objects.filter(is_deleted=False)
        if company_id:
            qs = qs.filter(company_id=company_id)
        return qs

    @action(detail=True, methods=['get', 'put', 'patch'])
    def payment_method(self, request, pk=None):
        """Get or update an employee's payment method. Callers must pass
        ?company_id= so ServiceKeyAuthentication can scope the queryset
        (GET requests have no body for it to read company_id from)."""
        employee = self.get_object()
        if request.method == 'GET':
            return Response(self.get_serializer(employee).data)
        serializer = self.get_serializer(employee, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class MyPayslipsView(views.APIView):
    """Employee self-service: own payslips (PWA). Replaces the PWA's old
    direct Supabase query against payroll_records/payroll_runs."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        employee_id = request.query_params.get('employee_id')
        if not employee_id:
            return Response({'error': 'employee_id is required'}, status=400)
        limit = int(request.query_params.get('limit', 24))
        records = (PayrollRecord.objects
                  .filter(employee_id=employee_id, is_deleted=False)
                  .select_related('payroll_run')
                  .order_by('-created_at')[:limit])
        return Response(MyPayslipSerializer(records, many=True).data)


class EmployeePayrollStatusViewSet(viewsets.GenericViewSet):
    """
    Get employees with their current period payment status.
    Used for the payroll dashboard employee table.
    """
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = EmployeeProfile.objects.filter(is_deleted=False, employment_status='active')
        # Company scoping is handled entirely by scope_employee_queryset, which
        # is role-aware: single-company roles get their home company (header),
        # cross-company admins get the switcher's selected company, and deployed
        # roles get their assigned employees. Pre-filtering by the home-company
        # header here would pin admins to their home company and make a
        # different company selection return nothing.
        from apps.core.permissions import scope_employee_queryset
        return scope_employee_queryset(qs, self.request)

    @action(detail=False, methods=['get'])
    def with_payment_status(self, request):
        """
        GET /api/employee-payroll-status/with-payment-status/

        Returns all active employees with their payment status for the current period.
        Also returns department payment status aggregations.

        Query params:
        - company_id: Filter by company (optional)
        """
        company_id = request.query_params.get('company_id')

        # Get current period
        now = timezone.now()
        current_month = now.month
        current_year = now.year

        # Get employees
        employees = self.get_queryset()
        if company_id:
            employees = employees.filter(company_id=company_id)

        # Get current period payroll run
        payroll_run = PayrollRun.objects.filter(
            period_month=current_month,
            period_year=current_year,
            is_deleted=False
        )
        if company_id:
            payroll_run = payroll_run.filter(company_id=company_id)
        payroll_run = payroll_run.order_by('-created_at').first()

        # Build payment status map from payroll records
        payment_status_map = {}
        if payroll_run:
            records = PayrollRecord.objects.filter(
                payroll_run=payroll_run,
                is_deleted=False
            ).values('employee_id', 'payment_status', 'paid_at')

            for record in records:
                payment_status_map[str(record['employee_id'])] = {
                    'status': record['payment_status'],
                    'paid_at': record['paid_at']
                }

        # Resolve employee names from the users (AppUser) table. Names link to
        # an employee primarily by users.employee_id == employee.id; fall back to
        # users.id == employee.user_id for legacy rows.
        from django.db import connection
        names_by_emp, names_by_user = {}, {}
        emp_ids = [str(e.id) for e in employees]
        user_ids = [str(e.user_id) for e in employees if e.user_id]
        with connection.cursor() as cursor:
            if emp_ids:
                ph = ','.join(['%s'] * len(emp_ids))
                cursor.execute(
                    f"SELECT employee_id, full_name FROM users "
                    f"WHERE employee_id IN ({ph})", emp_ids)
                for row in cursor.fetchall():
                    if row[0]:
                        names_by_emp[str(row[0])] = row[1]
            if user_ids:
                ph = ','.join(['%s'] * len(user_ids))
                cursor.execute(
                    f"SELECT id, full_name FROM users WHERE id IN ({ph})", user_ids)
                for row in cursor.fetchall():
                    names_by_user[str(row[0])] = row[1]

        # Per-employee statutory breakdown for the current month, so the payroll
        # table can show Gross / PAYE / NSSF / NHIF / HELB / Net per employee
        # (mirrors the run calculate()). Includes active allowances/deductions.
        import datetime as _dt
        from decimal import Decimal as _D

        from apps.hr.models import EmployeeAllowance, EmployeeDeduction
        _calc = KenyanTaxCalculator()
        _today = _dt.date.today()
        _first = _today.replace(day=1)
        _eids = [e.id for e in employees]
        _allow_by_emp, _ded_by_emp = {}, {}
        for _a in EmployeeAllowance.objects.filter(
                employee_id__in=_eids, is_active=True).select_related('allowance_type'):
            if _a.active_for(_today.year, _today.month):
                _allow_by_emp.setdefault(str(_a.employee_id), []).append(_a)
        for _d in EmployeeDeduction.objects.filter(employee_id__in=_eids, is_active=True):
            if (_d.effective_from <= _first.replace(day=28) and
                    (_d.effective_to is None or _d.effective_to >= _first)):
                _ded_by_emp.setdefault(str(_d.employee_id), []).append(_d)

        def _breakdown(emp):
            allows = _allow_by_emp.get(str(emp.id), [])
            taxable_allow = sum((a.amount for a in allows if a.allowance_type.taxable), _D('0'))
            nontax_allow = sum((a.amount for a in allows if not a.allowance_type.taxable), _D('0'))
            extra_ded = sum((d.amount for d in _ded_by_emp.get(str(emp.id), [])), _D('0'))
            base = emp.salary or _D('0')
            c = _calc.calculate_all(gross_pay=base + taxable_allow, helb_deduction=_D('0'))
            paye, nssf, nhif, helb = c['paye'], c['nssf_employee'], c['nhif'], c['helb']
            gross = base + taxable_allow + nontax_allow
            total = paye + nssf + nhif + helb + extra_ded
            return {'gross_salary': gross, 'paye': paye, 'nssf': nssf, 'nhif': nhif,
                    'helb': helb, 'other_deductions': extra_ded,
                    'total_deductions': total, 'net_salary': gross - total}

        # Build response data
        employee_data = []
        department_stats = {}

        for emp in employees:
            emp_id = str(emp.id)
            payment_info = payment_status_map.get(emp_id, {})
            payment_status = payment_info.get('status', 'pending')

            # Add user_full_name attribute for serializer (employee_id link
            # first, then user_id, then the job title as a last resort).
            emp.user_full_name = (names_by_emp.get(str(emp.id))
                                  or names_by_user.get(str(emp.user_id))
                                  or emp.job_title)
            emp.payment_status = payment_status
            emp.last_paid_at = payment_info.get('paid_at')

            employee_data.append({
                'id': emp.id,
                'employee_id': emp.id,
                'employee_name': emp.user_full_name,
                'employee_number': emp.employee_number,
                'department': emp.department,
                'salary': emp.salary,
                'payment_status': payment_status,
                'payment_method': emp.payment_method,
                'last_paid_at': emp.last_paid_at,
                **_breakdown(emp),
            })

            # Aggregate department stats
            dept = emp.department or 'Unassigned'
            if dept not in department_stats:
                department_stats[dept] = {'total': 0, 'paid': 0, 'pending': 0}
            department_stats[dept]['total'] += 1
            if payment_status == 'paid':
                department_stats[dept]['paid'] += 1
            else:
                department_stats[dept]['pending'] += 1

        # Build department status list
        departments = []
        for dept_name, stats in sorted(department_stats.items()):
            if stats['paid'] == 0:
                dept_status = 'none_paid'
            elif stats['paid'] == stats['total']:
                dept_status = 'all_paid'
            else:
                dept_status = 'partial'

            departments.append({
                'department': dept_name,
                'total_employees': stats['total'],
                'paid_count': stats['paid'],
                'pending_count': stats['pending'],
                'status': dept_status,
            })

        return Response({
            'data': employee_data,
            'departments': departments,
        })


class PaymentHistoryViewSet(viewsets.GenericViewSet):
    """
    Get historical payment records from completed payroll runs.
    """
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'])
    def list_history(self, request):
        """
        GET /api/payment-history/list-history/

        Returns historical payment records from completed/processing payroll runs.

        Query params:
        - company_id: Filter by company (optional)
        - limit: Number of records to return (default 100)
        """
        company_id = request.query_params.get('company_id')
        limit = int(request.query_params.get('limit', 100))

        # Get payroll records from completed runs
        records = PayrollRecord.objects.filter(
            is_deleted=False,
            payment_status__in=['paid', 'failed'],
            payroll_run__status__in=['completed', 'processing']
        ).select_related('employee', 'payroll_run').order_by('-paid_at')[:limit]

        if company_id:
            records = records.filter(payroll_run__company_id=company_id)

        # Get user names
        from django.db import connection
        user_ids = list(set(r.employee.user_id for r in records))
        user_names = {}
        if user_ids:
            with connection.cursor() as cursor:
                placeholders = ','.join(['%s'] * len(user_ids))
                cursor.execute(
                    f"SELECT id, full_name FROM users WHERE id IN ({placeholders})",
                    user_ids
                )
                for row in cursor.fetchall():
                    user_names[str(row[0])] = row[1]

        # Build response
        history_data = []
        for record in records:
            emp = record.employee
            run = record.payroll_run

            history_data.append({
                'id': record.id,
                'employee_id': emp.id,
                'employee_name': user_names.get(str(emp.user_id), emp.job_title),
                'employee_number': emp.employee_number,
                'department': emp.department,
                'amount': record.net_salary,
                'payment_method': record.payment_method,
                'payment_date': record.paid_at,
                'reference': record.payment_reference,
                'status': 'paid' if record.payment_status == 'paid' else 'failed',
                'period_month': run.period_month,
                'period_year': run.period_year,
            })

        return Response({'data': history_data})


class PesaPalConfigViewSet(viewsets.GenericViewSet):
    """
    PesaPal configuration management.

    Credentials are loaded from environment variables:
    - PESAPAL_CONSUMER_KEY
    - PESAPAL_CONSUMER_SECRET
    - PESAPAL_IPN_ID
    - PESAPAL_SANDBOX
    """
    permission_classes = [IsAuthenticated]

    def get_pesapal(self):
        """Get PesaPal service instance with credentials from env vars"""
        pesapal = PesaPalService()
        if not pesapal.consumer_key or not pesapal.consumer_secret:
            return None
        return pesapal

    @action(detail=False, methods=['post'])
    def register_ipn(self, request):
        """
        Register IPN URL with PesaPal.
        Call this once to set up payment notifications.

        The IPN ID will be returned and should be added to your .env file
        as PESAPAL_IPN_ID.

        Request body:
        {
            "callback_url": "https://yourdomain.com/api/pesapal/ipn/"
        }
        """
        callback_url = request.data.get('callback_url')
        if not callback_url:
            return Response(
                {'error': 'callback_url is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        pesapal = self.get_pesapal()
        if not pesapal:
            return Response(
                {'error': 'PesaPal credentials not configured in environment variables'},
                status=status.HTTP_400_BAD_REQUEST
            )

        result = pesapal.register_ipn(callback_url)

        if result.get('success'):
            return Response({
                'message': 'IPN registered successfully. Add the ipn_id to your .env file as PESAPAL_IPN_ID',
                'ipn_id': result.get('ipn_id'),
                'url': result.get('url')
            })
        else:
            return Response(
                {'error': result.get('error', 'IPN registration failed')},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=False, methods=['get'])
    def list_ipns(self, request):
        """Get list of registered IPN URLs"""
        pesapal = self.get_pesapal()
        if not pesapal:
            return Response(
                {'error': 'PesaPal credentials not configured in environment variables'},
                status=status.HTTP_400_BAD_REQUEST
            )

        result = pesapal.get_registered_ipns()
        return Response(result)

    @action(detail=False, methods=['get'])
    def transaction_status(self, request):
        """
        Check status of a specific transaction.

        Query params:
        - order_tracking_id: PesaPal order tracking ID
        """
        order_tracking_id = request.query_params.get('order_tracking_id')
        if not order_tracking_id:
            return Response(
                {'error': 'order_tracking_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        pesapal = self.get_pesapal()
        if not pesapal:
            return Response(
                {'error': 'PesaPal credentials not configured in environment variables'},
                status=status.HTTP_400_BAD_REQUEST
            )

        result = pesapal.get_transaction_status(order_tracking_id)
        return Response(result)

    @action(detail=False, methods=['get'])
    def config_status(self, request):
        """Check if PesaPal is properly configured"""
        pesapal = PesaPalService()
        return Response({
            'configured': bool(pesapal.consumer_key and pesapal.consumer_secret),
            'sandbox': pesapal.sandbox,
            'ipn_configured': bool(pesapal.ipn_id),
        })


@method_decorator(csrf_exempt, name='dispatch')
class PesaPalIPNWebhook(views.APIView):
    """
    PesaPal IPN (Instant Payment Notification) webhook endpoint.
    Receives payment status updates from PesaPal.

    This endpoint must be publicly accessible and registered with PesaPal.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        """
        Handle GET IPN callbacks.
        PesaPal sends: OrderTrackingId, OrderMerchantReference, OrderNotificationType
        """
        order_tracking_id = request.query_params.get('OrderTrackingId')
        merchant_reference = request.query_params.get('OrderMerchantReference')
        notification_type = request.query_params.get('OrderNotificationType')

        logger.info(
            f"PesaPal IPN GET: tracking_id={order_tracking_id}, "
            f"merchant_ref={merchant_reference}, type={notification_type}"
        )

        if not order_tracking_id:
            return Response({'status': 'error', 'message': 'Missing OrderTrackingId'})

        # Query PesaPal for actual status using env var credentials
        pesapal = PesaPalService()

        if pesapal.consumer_key and pesapal.consumer_secret:
            try:
                status_result = pesapal.get_transaction_status(order_tracking_id)

                if status_result.get('success'):
                    payment_status = status_result.get('payment_status', 'PENDING')
                    confirmation_code = status_result.get('confirmation_code')

                    # Process asynchronously
                    process_ipn_callback.delay(
                        order_tracking_id=order_tracking_id,
                        payment_status=payment_status,
                        confirmation_code=confirmation_code
                    )
            except Exception as e:
                logger.exception(f"Failed to process IPN for {order_tracking_id}: {e}")
        else:
            logger.error("PesaPal credentials not configured for IPN processing")

        # Always return success to PesaPal
        return Response({
            'orderNotificationType': notification_type,
            'orderTrackingId': order_tracking_id,
            'orderMerchantReference': merchant_reference,
            'status': 200
        })

    def post(self, request):
        """
        Handle POST IPN callbacks.
        """
        order_tracking_id = request.data.get('OrderTrackingId')
        merchant_reference = request.data.get('OrderMerchantReference')
        notification_type = request.data.get('OrderNotificationType')

        logger.info(
            f"PesaPal IPN POST: tracking_id={order_tracking_id}, "
            f"merchant_ref={merchant_reference}, type={notification_type}"
        )

        if not order_tracking_id:
            return Response({'status': 'error', 'message': 'Missing OrderTrackingId'})

        # Query PesaPal for actual status using env var credentials
        pesapal = PesaPalService()

        if pesapal.consumer_key and pesapal.consumer_secret:
            try:
                status_result = pesapal.get_transaction_status(order_tracking_id)

                if status_result.get('success'):
                    payment_status = status_result.get('payment_status', 'PENDING')
                    confirmation_code = status_result.get('confirmation_code')

                    # Process asynchronously
                    process_ipn_callback.delay(
                        order_tracking_id=order_tracking_id,
                        payment_status=payment_status,
                        confirmation_code=confirmation_code
                    )
            except Exception as e:
                logger.exception(f"Failed to process IPN for {order_tracking_id}: {e}")
        else:
            logger.error("PesaPal credentials not configured for IPN processing")

        # Always return success to PesaPal
        return Response({
            'orderNotificationType': notification_type,
            'orderTrackingId': order_tracking_id,
            'orderMerchantReference': merchant_reference,
            'status': 200
        })


class IntaSendConfigViewSet(viewsets.GenericViewSet):
    """
    IntaSend configuration and transaction status management.

    IntaSend is used as the primary M-Pesa B2C payment provider.
    Credentials are loaded from environment variables:
    - INTASEND_PUBLISHABLE_KEY
    - INTASEND_SECRET_KEY
    - INTASEND_SANDBOX
    """
    permission_classes = [IsAuthenticated]

    def get_intasend(self):
        """Get IntaSend service instance"""
        intasend = IntaSendService()
        if not intasend.secret_key:
            return None
        return intasend

    @action(detail=False, methods=['get'])
    def config_status(self, request):
        """
        Check if IntaSend is properly configured.

        GET /api/intasend/config-status/

        Returns:
        - configured: bool - Whether IntaSend credentials are set
        - sandbox: bool - Whether sandbox mode is enabled
        - provider: str - Always 'intasend'
        """
        intasend = IntaSendService()
        return Response({
            'configured': bool(intasend.secret_key and intasend.publishable_key),
            'sandbox': intasend.sandbox,
            'provider': 'intasend',
        })

    @action(detail=False, methods=['get'])
    def transaction_status(self, request):
        """
        Check status of a specific IntaSend transaction.

        GET /api/intasend/transaction-status/?tracking_id=xxx

        Query params:
        - tracking_id: IntaSend transaction tracking ID

        Returns transaction status information.
        """
        tracking_id = request.query_params.get('tracking_id')
        if not tracking_id:
            return Response(
                {'error': 'tracking_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        intasend = self.get_intasend()
        if not intasend:
            return Response(
                {'error': 'IntaSend credentials not configured'},
                status=status.HTTP_400_BAD_REQUEST
            )

        result = intasend.get_transaction_status(tracking_id)
        return Response(result)

    @action(detail=False, methods=['get'])
    def wallet_balance(self, request):
        """
        Get IntaSend wallet balance.

        GET /api/intasend/wallet-balance/

        Returns the current wallet balance for disbursements.
        """
        intasend = self.get_intasend()
        if not intasend:
            return Response(
                {'error': 'IntaSend credentials not configured'},
                status=status.HTTP_400_BAD_REQUEST
            )

        result = intasend.get_wallet_balance()
        return Response(result)

    @action(detail=False, methods=['post'], url_path='send-mpesa')
    def send_mpesa(self, request):
        """
        Send M-Pesa B2C payment via IntaSend.

        POST /api/intasend/send-mpesa/

        Body:
        - phone: Recipient phone number (required)
        - amount: Amount in KES (required)
        - name: Recipient name (optional, default: "Employee")
        - reference: Payment reference (optional, auto-generated if not provided)
        - narrative: Payment description (optional, default: "Salary Payment")

        Returns payment initiation result with tracking_id.
        """
        intasend = self.get_intasend()
        if not intasend:
            return Response(
                {'success': False, 'error': 'IntaSend credentials not configured'},
                status=status.HTTP_400_BAD_REQUEST
            )

        phone = request.data.get('phone')
        amount = request.data.get('amount')
        name = request.data.get('name', 'Employee')
        reference = request.data.get('reference', f'PAY-{int(__import__("time").time())}')
        narrative = request.data.get('narrative', 'Salary Payment')

        if not phone:
            return Response(
                {'success': False, 'error': 'phone is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not amount:
            return Response(
                {'success': False, 'error': 'amount is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            amount = float(amount)
        except (ValueError, TypeError):
            return Response(
                {'success': False, 'error': 'Invalid amount'},
                status=status.HTTP_400_BAD_REQUEST
            )

        logger.info(f"[send-mpesa] Sending KES {amount} to {phone} via IntaSend")

        result = intasend.send_mpesa(
            phone=phone,
            amount=amount,
            reference=reference,
            name=name,
            narrative=narrative
        )

        logger.info(f"[send-mpesa] Result: {result}")

        if result.get('success'):
            return Response(result)
        else:
            return Response(result, status=status.HTTP_400_BAD_REQUEST)


class ProfilePictureView(views.APIView):
    """
    POST /api/me/profile-picture/
    Body: {
      "image_b64": "<base64, no data: prefix>",
      "user_id": "<uuid>",
      "face_descriptor": [<128 floats>]   # optional — sent by face-api.js on the PWA
    }
    Saves the data URL and face descriptor. When face_descriptor is present
    SmileID enrollment is skipped (face-api.js handles verification client-side).
    """

    def post(self, request):
        user_id = request.data.get('user_id') or request_user_id(request)
        image_b64 = request.data.get('image_b64', '').strip()
        if not user_id or not image_b64:
            return Response({'error': 'user_id and image_b64 are required'},
                            status=status.HTTP_400_BAD_REQUEST)

        # Strip data URL prefix if present ("data:image/jpeg;base64,...")
        if ',' in image_b64:
            image_b64 = image_b64.split(',', 1)[1]

        data_url = f'data:image/jpeg;base64,{image_b64}'
        face_descriptor = request.data.get('face_descriptor')  # list of 128 floats or None

        update_fields = {'profile_picture_url': data_url}
        if face_descriptor is not None:
            update_fields['face_descriptor'] = face_descriptor

        updated = EmployeeProfile.objects.filter(
            user_id=user_id, is_deleted=False,
        ).update(**update_fields)

        if not updated:
            return Response({'error': 'Employee profile not found'},
                            status=status.HTTP_404_NOT_FOUND)

        # Only call SmileID when no face_descriptor was provided (legacy path /
        # when SMILEID_DEMO_MODE=False and SmileID credentials are configured).
        enrollment: dict = {}
        if face_descriptor is None:
            from apps.attendance.services import smileid
            try:
                enrollment = smileid.enroll_face(str(user_id), image_b64)
            except smileid.SmileIDError as exc:
                logger.warning('SmileID enrollment failed for user %s: %s', user_id, exc)
                enrollment = {'enrolled': False, 'error': str(exc)}

        ServiceAuditLog.log(
            'employee.profile_picture_updated', request=request,
            object_type='EmployeeProfile', object_id=str(user_id),
            metadata={
                'face_enrolled': face_descriptor is not None,
                'smileid_enrolled': enrollment.get('enrolled', False),
            })

        return Response({
            'ok': True,
            'face_enrolled': face_descriptor is not None,
            'smileid': enrollment,
        })
