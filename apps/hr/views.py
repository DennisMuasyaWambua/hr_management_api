"""
HR API: allowances, deductions, overtime, reimbursements, statutory rates,
minimum wage compliance, disciplinary, exits, leave recalls, certificates.
"""
from django.utils import timezone
from rest_framework import status, views, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.models import OneTapToken, ServiceAuditLog
from apps.core.permissions import (HasModulePermission, IsHighestRank,
                                   request_company_id, request_user_id)
from apps.core.services import notifications as notif

from .models import (AllowanceType, Announcement, BackgroundCheck,
                     ComplianceAlert, DeductionType, DisciplinaryRecord,
                     EmployeeAllowance, EmployeeCertificate,
                     EmployeeDeduction, EmployeeExit, ExitClearance,
                     EmployeeOnboardingDocument, ExitClearanceItem,
                     KpiAssignment, LeaveBalance, LeaveRecall, LeaveRequest,
                     MedicalRecord, MinimumWage, OvertimeRequest,
                     PerformanceReview, Reimbursement, StatutoryRate,
                     TrainingEnrollment, TrainingSession)
from .serializers import (AllowanceTypeSerializer, AnnouncementSerializer,
                          BackgroundCheckSerializer, ComplianceAlertSerializer,
                          DeductionTypeSerializer, DisciplinaryRecordSerializer,
                          EmployeeAllowanceSerializer,
                          EmployeeCertificateSerializer,
                          EmployeeDeductionSerializer, EmployeeExitSerializer,
                          ExitClearanceSerializer,
                          EmployeeOnboardingDocumentSerializer,
                          ExitClearanceItemSerializer, KpiAssignmentSerializer,
                          LeaveBalanceSerializer, LeaveRecallSerializer,
                          LeaveRequestSerializer, MedicalRecordSerializer,
                          MinimumWageSerializer, OvertimeRequestSerializer,
                          PerformanceReviewSerializer, ReimbursementSerializer,
                          StatutoryRateSerializer, TrainingEnrollmentSerializer,
                          TrainingSessionSerializer)


class CompanyScopedViewSet(viewsets.ModelViewSet):
    """Filters by company_id header/param; stamps company + actor on create."""
    permission_classes = [HasModulePermission]

    def get_queryset(self):
        qs = self.queryset
        company_id = request_company_id(self.request)
        if company_id:
            qs = qs.filter(company_id=company_id)
        employee_id = self.request.query_params.get('employee_id')
        if employee_id and hasattr(qs.model, 'employee_id'):
            qs = qs.filter(employee_id=employee_id)
        return qs

    def perform_create(self, serializer):
        kwargs = {}
        company_id = request_company_id(self.request)
        if company_id and hasattr(serializer.Meta.model, 'company_id'):
            kwargs['company_id'] = serializer.validated_data.get('company_id') or company_id
        instance = serializer.save(**kwargs)
        ServiceAuditLog.log(
            f'{self.rbac_module}.created', request=self.request,
            object_type=instance.__class__.__name__, object_id=str(instance.id),
            company_id=getattr(instance, 'company_id', None))


# --- Allowances / deductions -------------------------------------------------

class AllowanceTypeViewSet(CompanyScopedViewSet):
    queryset = AllowanceType.objects.all()
    serializer_class = AllowanceTypeSerializer
    rbac_module = 'allowances'


class EmployeeAllowanceViewSet(CompanyScopedViewSet):
    queryset = EmployeeAllowance.objects.select_related('allowance_type')
    serializer_class = EmployeeAllowanceSerializer
    rbac_module = 'allowances'


class DeductionTypeViewSet(CompanyScopedViewSet):
    queryset = DeductionType.objects.all()
    serializer_class = DeductionTypeSerializer
    rbac_module = 'allowances'


class EmployeeDeductionViewSet(CompanyScopedViewSet):
    queryset = EmployeeDeduction.objects.select_related('deduction_type')
    serializer_class = EmployeeDeductionSerializer
    rbac_module = 'allowances'


# --- Overtime ----------------------------------------------------------------

class OvertimeRequestViewSet(CompanyScopedViewSet):
    queryset = OvertimeRequest.objects.all()
    serializer_class = OvertimeRequestSerializer
    rbac_module = 'overtime'

    def perform_create(self, serializer):
        super().perform_create(serializer)
        ot = serializer.instance
        # Notify the manager with a one-tap approval link (SMS + email).
        if ot.manager_id:
            token = OneTapToken.issue('overtime.approve', ot.id, ot.manager_id,
                                      company_id=ot.company_id, tenant_id=ot.tenant_id)
            manager = self._contact(ot.manager_id)
            if manager:
                notif.notify('overtime.requested', [manager], {
                    'employee_name': str(ot.employee_id)[:8],
                    'hours': str(ot.hours), 'date': str(ot.date),
                    'approve_url': _one_tap_url(token),
                }, channels=('email', 'sms'), company_id=ot.company_id,
                    related=('overtime_request', ot.id))

    @staticmethod
    def _contact(user_id):
        from apps.payroll.models import EmployeeProfile
        emp = EmployeeProfile.objects.filter(user_id=user_id).first()
        if emp is None:
            return None
        return {'email': None, 'phone': emp.mpesa_number or emp.next_of_kin_phone}

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        ot = self.get_object()
        if ot.status != 'pending':
            return Response({'error': f'Already {ot.status}'},
                            status=status.HTTP_409_CONFLICT)
        ot.decide('approved', request_user_id(request))
        ServiceAuditLog.log('overtime.approved', request=request,
                            object_type='OvertimeRequest', object_id=str(ot.id),
                            company_id=ot.company_id)
        return Response(self.get_serializer(ot).data)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        ot = self.get_object()
        if ot.status != 'pending':
            return Response({'error': f'Already {ot.status}'},
                            status=status.HTTP_409_CONFLICT)
        ot.decide('rejected', request_user_id(request))
        ServiceAuditLog.log('overtime.rejected', request=request,
                            object_type='OvertimeRequest', object_id=str(ot.id),
                            company_id=ot.company_id)
        return Response(self.get_serializer(ot).data)

    @action(detail=False, methods=['get'])
    def pending_for_manager(self, request):
        """PWA manager profile: my pending approvals."""
        manager_id = request.query_params.get('manager_id') or request_user_id(request)
        qs = self.get_queryset().filter(status='pending', manager_id=manager_id)
        return Response(self.get_serializer(qs, many=True).data)


# --- Reimbursements ----------------------------------------------------------

class ReimbursementViewSet(CompanyScopedViewSet):
    queryset = Reimbursement.objects.all()
    serializer_class = ReimbursementSerializer
    rbac_module = 'reimbursements'

    @action(detail=True, methods=['post'])
    def process(self, request, pk=None):
        """HR approves/rejects/marks-paid. Body: {"decision": "approved"|"rejected"|"paid", "payment_reference": "..."}"""
        r = self.get_object()
        decision = request.data.get('decision')
        if decision not in ('approved', 'rejected', 'paid'):
            return Response({'error': 'decision must be approved|rejected|paid'},
                            status=status.HTTP_400_BAD_REQUEST)
        if r.status == 'paid':
            return Response({'error': 'Already paid'}, status=status.HTTP_409_CONFLICT)
        r.status = decision
        r.processed_by = request_user_id(request)
        r.processed_at = timezone.now()
        r.payment_reference = request.data.get('payment_reference', r.payment_reference)
        r.save()
        ServiceAuditLog.log(f'reimbursements.{decision}', request=request,
                            object_type='Reimbursement', object_id=str(r.id),
                            company_id=r.company_id,
                            metadata={'amount': str(r.amount)})
        return Response(self.get_serializer(r).data)


# --- Statutory rates & compliance ---------------------------------------------

class StatutoryRateViewSet(CompanyScopedViewSet):
    queryset = StatutoryRate.objects.all()
    serializer_class = StatutoryRateSerializer
    rbac_module = 'statutory_rates'
    # Only the highest rank may change statutory rates (super admin page).
    permission_classes = [IsHighestRank]

    @action(detail=False, methods=['get'])
    def current(self, request):
        """All rate kinds effective today (company override aware)."""
        today = timezone.localdate()
        company_id = request_company_id(request)
        out = {}
        for kind, _ in StatutoryRate.RATE_KINDS:
            row = StatutoryRate.effective(kind, today, company_id)
            if row:
                out[kind] = {'value': row.value, 'effective_from': row.effective_from,
                             'id': str(row.id)}
        return Response(out)


class MinimumWageViewSet(viewsets.ModelViewSet):
    queryset = MinimumWage.objects.all()
    serializer_class = MinimumWageSerializer
    permission_classes = [IsHighestRank]
    rbac_module = 'compliance'
    pagination_class = None


class ComplianceAlertViewSet(CompanyScopedViewSet):
    queryset = ComplianceAlert.objects.all()
    serializer_class = ComplianceAlertSerializer
    rbac_module = 'compliance'
    http_method_names = ['get', 'patch', 'head', 'options']


# --- Disciplinary & exits ------------------------------------------------------

class DisciplinaryRecordViewSet(CompanyScopedViewSet):
    queryset = DisciplinaryRecord.objects.all()
    serializer_class = DisciplinaryRecordSerializer
    rbac_module = 'disciplinary'

    @action(detail=True, methods=['post'])
    def escalate(self, request, pk=None):
        """Escalate per Employment Act chain: pip → warning_letter → salary_penalty/suspension → termination_recommendation."""
        rec = self.get_object()
        next_kind = request.data.get('kind')
        valid_next = {'pip': ['warning_letter'],
                      'verbal_warning': ['warning_letter'],
                      'warning_letter': ['salary_penalty', 'suspension',
                                         'termination_recommendation'],
                      'salary_penalty': ['termination_recommendation'],
                      'suspension': ['termination_recommendation']}
        if next_kind not in valid_next.get(rec.kind, []):
            return Response(
                {'error': f'Cannot escalate {rec.kind} to {next_kind}. '
                          f'Allowed: {valid_next.get(rec.kind, [])}'},
                status=status.HTTP_400_BAD_REQUEST)
        rec.status = 'escalated'
        rec.save(update_fields=['status', 'updated_at'])
        new_rec = DisciplinaryRecord.objects.create(
            employee_id=rec.employee_id, company_id=rec.company_id,
            tenant_id=rec.tenant_id, kind=next_kind,
            title=request.data.get('title', f'Escalated from {rec.get_kind_display()}'),
            description=request.data.get('description', ''),
            issued_by=request_user_id(request), escalated_from=rec)
        ServiceAuditLog.log('disciplinary.escalated', request=request,
                            object_type='DisciplinaryRecord', object_id=str(new_rec.id),
                            company_id=rec.company_id,
                            metadata={'from': rec.kind, 'to': next_kind})
        return Response(self.get_serializer(new_rec).data,
                        status=status.HTTP_201_CREATED)


DEFAULT_CLEARANCE_ITEMS = ['Company equipment returned', 'Finance clearance',
                           'IT access revoked', 'Gate pass / ID returned',
                           'Handover completed']


class EmployeeExitViewSet(CompanyScopedViewSet):
    queryset = EmployeeExit.objects.prefetch_related('clearance_items')
    serializer_class = EmployeeExitSerializer
    rbac_module = 'exits'

    def perform_create(self, serializer):
        super().perform_create(serializer)
        exit_ = serializer.instance
        for item in DEFAULT_CLEARANCE_ITEMS:
            ExitClearanceItem.objects.create(exit=exit_, item=item)

    @action(detail=True, methods=['post'])
    def clear_item(self, request, pk=None):
        exit_ = self.get_object()
        item_id = request.data.get('item_id')
        try:
            item = exit_.clearance_items.get(id=item_id)
        except ExitClearanceItem.DoesNotExist:
            return Response({'error': 'Item not found'},
                            status=status.HTTP_404_NOT_FOUND)
        item.is_cleared = True
        item.cleared_by = request_user_id(request)
        item.cleared_at = timezone.now()
        item.notes = request.data.get('notes', item.notes)
        item.save()
        if not exit_.clearance_items.filter(is_cleared=False).exists() \
                and exit_.status in ('initiated', 'clearance'):
            exit_.status = 'final_dues'
            exit_.save(update_fields=['status', 'updated_at'])
        return Response(EmployeeExitSerializer(exit_).data)

    @action(detail=True, methods=['post'])
    def compute_final_dues(self, request, pk=None):
        """
        Final dues per Employment Act inputs supplied by HR:
        pro-rata salary days, accrued leave days, notice pay, service pay.
        Body: {"prorata_days": n, "accrued_leave_days": n, "notice_pay": x, "service_pay": x}
        """
        from decimal import Decimal
        from apps.payroll.models import EmployeeProfile
        exit_ = self.get_object()
        emp = EmployeeProfile.objects.filter(id=exit_.employee_id).first()
        if emp is None:
            return Response({'error': 'Employee not found'},
                            status=status.HTTP_404_NOT_FOUND)
        daily = Decimal(emp.salary) / Decimal(30)
        prorata = daily * Decimal(str(request.data.get('prorata_days', 0)))
        leave_pay = daily * Decimal(str(request.data.get('accrued_leave_days', 0)))
        notice_pay = Decimal(str(request.data.get('notice_pay', 0)))
        service_pay = Decimal(str(request.data.get('service_pay', 0)))
        total = prorata + leave_pay + notice_pay + service_pay
        exit_.final_dues = {
            'prorata_salary': str(prorata.quantize(Decimal('0.01'))),
            'accrued_leave_pay': str(leave_pay.quantize(Decimal('0.01'))),
            'notice_pay': str(notice_pay), 'service_pay': str(service_pay),
            'computed_at': timezone.now().isoformat(),
            'computed_by': request_user_id(request),
        }
        exit_.final_dues_total = total
        exit_.save(update_fields=['final_dues', 'final_dues_total', 'updated_at'])
        ServiceAuditLog.log('exits.final_dues_computed', request=request,
                            object_type='EmployeeExit', object_id=str(exit_.id),
                            company_id=exit_.company_id,
                            metadata={'total': str(total)})
        return Response(self.get_serializer(exit_).data)


# --- Leave recall ---------------------------------------------------------------

class LeaveRecallViewSet(CompanyScopedViewSet):
    queryset = LeaveRecall.objects.all()
    serializer_class = LeaveRecallSerializer
    rbac_module = 'leave'

    def perform_create(self, serializer):
        super().perform_create(serializer)
        recall = serializer.instance
        if recall.manager_id:
            token = OneTapToken.issue('leave_recall.approve', recall.id,
                                      recall.manager_id, company_id=recall.company_id,
                                      tenant_id=recall.tenant_id)
            notif.notify('leave.recall_requested',
                         [{'phone': None, 'email': None}],  # contacts resolved by dashboard; log only
                         {'employee_name': str(recall.employee_id)[:8],
                          'start_date': '', 'end_date': '',
                          'approve_url': _one_tap_url(token)},
                         channels=('email',), company_id=recall.company_id,
                         related=('leave_recall', recall.id))

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        recall = self.get_object()
        if recall.status != 'pending':
            return Response({'error': f'Already {recall.status}'},
                            status=status.HTTP_409_CONFLICT)
        recall.approve(request_user_id(request))
        ServiceAuditLog.log('leave.recall_approved', request=request,
                            object_type='LeaveRecall', object_id=str(recall.id),
                            company_id=recall.company_id)
        return Response(self.get_serializer(recall).data)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        recall = self.get_object()
        if recall.status != 'pending':
            return Response({'error': f'Already {recall.status}'},
                            status=status.HTTP_409_CONFLICT)
        recall.reject(request_user_id(request))
        return Response(self.get_serializer(recall).data)


# --- Certificates ----------------------------------------------------------------

class EmployeeCertificateViewSet(CompanyScopedViewSet):
    queryset = EmployeeCertificate.objects.all()
    serializer_class = EmployeeCertificateSerializer
    rbac_module = 'certificates'

    @action(detail=False, methods=['get'])
    def expiring(self, request):
        """Certificates expiring within ?days= (default 30) — dashboard badge."""
        days = int(request.query_params.get('days', 30))
        cutoff = timezone.localdate() + timezone.timedelta(days=days)
        qs = self.get_queryset().filter(is_active=True,
                                        expiry_date__isnull=False,
                                        expiry_date__lte=cutoff)
        return Response(self.get_serializer(qs, many=True).data)


# --- Leave & announcements (employee self-service, PWA) --------------------

class LeaveRequestViewSet(CompanyScopedViewSet):
    queryset = LeaveRequest.objects.filter(is_deleted=False)
    serializer_class = LeaveRequestSerializer
    rbac_module = 'leave'

    def get_queryset(self):
        from django.db.models import OuterRef, Subquery
        from apps.core.models import AppUser
        qs = super().get_queryset().annotate(
            employee_name=Subquery(
                AppUser.objects.filter(id=OuterRef('employee_id')).values('full_name')[:1]
            )
        )
        p = self.request.query_params
        if p.get('status'):
            qs = qs.filter(status=p['status'])
        if p.get('leave_type'):
            qs = qs.filter(leave_type=p['leave_type'])
        if p.get('employee_id'):
            qs = qs.filter(employee_id=p['employee_id'])
        if p.get('start_date_before'):
            qs = qs.filter(start_date__lte=p['start_date_before'])
        if p.get('end_date_after'):
            qs = qs.filter(end_date__gte=p['end_date_after'])
        if p.get('start_date_after'):
            qs = qs.filter(start_date__gte=p['start_date_after'])
        if p.get('end_date_before'):
            qs = qs.filter(end_date__lte=p['end_date_before'])
        return qs.order_by('-created_at')

    def _employee_contact(self, employee_id):
        """Return {'email': ..., 'phone': ...} for the employee, or None."""
        from apps.payroll.models import EmployeeProfile
        from apps.core.models import AppUser
        emp = EmployeeProfile.objects.filter(id=employee_id, is_deleted=False).first()
        if emp is None:
            return None
        user = AppUser.objects.filter(id=emp.user_id).first()
        return {
            'email': user.email if user else None,
            'phone': emp.mpesa_number or emp.next_of_kin_phone,
            'full_name': user.full_name if user else str(employee_id)[:8],
            'manager_id': emp.manager_id,
        }

    def _manager_contact(self, manager_id):
        """Return {'email': ..., 'phone': ...} for the manager, or None."""
        from apps.payroll.models import EmployeeProfile
        from apps.core.models import AppUser
        emp = EmployeeProfile.objects.filter(user_id=manager_id, is_deleted=False).first()
        user = AppUser.objects.filter(id=manager_id).first()
        return {
            'email': user.email if user else None,
            'phone': emp.mpesa_number if emp else None,
        }

    def perform_create(self, serializer):
        super().perform_create(serializer)
        leave = serializer.instance
        if not leave.company_id:
            return

        ctx = {
            'leave_type': leave.leave_type,
            'start_date': str(leave.start_date),
            'end_date': str(leave.end_date),
            'days_requested': str(leave.days_requested),
            'reason': leave.reason,
        }

        # 1. Notify the employee's direct manager (one-tap approve link)
        emp_info = self._employee_contact(leave.employee_id)
        employee_name = emp_info['full_name'] if emp_info else 'Employee'
        ctx['employee_name'] = employee_name

        manager_notified = False
        if emp_info and emp_info.get('manager_id'):
            manager = self._manager_contact(emp_info['manager_id'])
            if manager and (manager['email'] or manager['phone']):
                token = OneTapToken.issue(
                    'leave.approve', leave.id, emp_info['manager_id'],
                    company_id=leave.company_id, tenant_id=leave.tenant_id)
                ctx['approve_url'] = _one_tap_url(token)
                notif.notify('leave.requested', [manager], ctx,
                             channels=('email', 'sms'),
                             company_id=leave.company_id,
                             tenant_id=leave.tenant_id,
                             related=('leave', leave.id))
                manager_notified = True

        # 2. Always notify HR/admins as well (email only)
        from apps.core.models import AppUser
        hr_recipients = [
            {'email': u.email} for u in
            AppUser.objects.filter(company_id=leave.company_id,
                                   role__in=['hr_admin', 'super_admin'],
                                   is_deleted=False)[:10]
            if u.email
        ]
        if hr_recipients:
            notif.notify('leave.requested', hr_recipients, ctx,
                         channels=('email',), company_id=leave.company_id,
                         tenant_id=leave.tenant_id, related=('leave', leave.id))

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        leave = self.get_object()
        if leave.status != 'pending':
            return Response({'error': f'Already {leave.status}'},
                            status=status.HTTP_409_CONFLICT)
        leave.approve(request_user_id(request))
        ServiceAuditLog.log('leave.approved', request=request,
                            object_type='LeaveRequest', object_id=str(leave.id),
                            company_id=leave.company_id)
        # Notify the employee of the decision
        emp_info = self._employee_contact(leave.employee_id)
        if emp_info and (emp_info['email'] or emp_info['phone']):
            notif.notify('leave.approved', [emp_info], {
                'employee_name': emp_info['full_name'],
                'leave_type': leave.leave_type,
                'start_date': str(leave.start_date),
                'end_date': str(leave.end_date),
                'days_requested': str(leave.days_requested),
            }, channels=('email', 'sms'), company_id=leave.company_id,
            tenant_id=leave.tenant_id, related=('leave', leave.id))
        return Response(self.get_serializer(leave).data)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        leave = self.get_object()
        if leave.status != 'pending':
            return Response({'error': f'Already {leave.status}'},
                            status=status.HTTP_409_CONFLICT)
        rejection_reason = request.data.get('rejection_reason', '')
        leave.reject(request_user_id(request), rejection_reason)
        ServiceAuditLog.log('leave.rejected', request=request,
                            object_type='LeaveRequest', object_id=str(leave.id),
                            company_id=leave.company_id)
        # Notify the employee of the rejection
        emp_info = self._employee_contact(leave.employee_id)
        if emp_info and (emp_info['email'] or emp_info['phone']):
            notif.notify('leave.rejected', [emp_info], {
                'employee_name': emp_info['full_name'],
                'leave_type': leave.leave_type,
                'start_date': str(leave.start_date),
                'end_date': str(leave.end_date),
                'days_requested': str(leave.days_requested),
                'rejection_reason': rejection_reason or 'No reason provided',
            }, channels=('email', 'sms'), company_id=leave.company_id,
            tenant_id=leave.tenant_id, related=('leave', leave.id))
        return Response(self.get_serializer(leave).data)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Employee cancels their own pending request."""
        leave = self.get_object()
        if leave.status != 'pending':
            return Response({'error': 'Only pending requests can be cancelled'},
                            status=status.HTTP_409_CONFLICT)
        leave.status = 'cancelled'
        leave.save(update_fields=['status', 'updated_at'])
        ServiceAuditLog.log('leave.cancelled', request=request,
                            object_type='LeaveRequest', object_id=str(leave.id),
                            company_id=leave.company_id)
        return Response(self.get_serializer(leave).data)


class LeaveBalanceViewSet(CompanyScopedViewSet):
    http_method_names = ['get', 'head', 'options']
    queryset = LeaveBalance.objects.filter(is_deleted=False)
    serializer_class = LeaveBalanceSerializer
    rbac_module = 'leave'

    def get_queryset(self):
        qs = super().get_queryset()
        year = self.request.query_params.get('year')
        if year:
            qs = qs.filter(year=year)
        return qs


class AnnouncementViewSet(CompanyScopedViewSet):
    http_method_names = ['get', 'post', 'head', 'options']
    queryset = Announcement.objects.filter(is_deleted=False)
    serializer_class = AnnouncementSerializer
    # Announcements are company-wide notices; reads are open to any
    # authenticated company member (company scoping restricts the rows).
    # Writes still require the notifications.manage grant (HR/admin tier).
    rbac_module = 'notifications'

    def get_queryset(self):
        from django.db.models import Q
        qs = super().get_queryset().filter(
            Q(expires_at__isnull=True) | Q(expires_at__gte=timezone.now()))
        department = self.request.query_params.get('department')
        if department:
            qs = qs.filter(Q(department__isnull=True) | Q(department=department))
        return qs


# --- Medical, background checks, performance, training ---------------------

class MedicalRecordViewSet(CompanyScopedViewSet):
    queryset = MedicalRecord.objects.filter(is_deleted=False)
    serializer_class = MedicalRecordSerializer
    rbac_module = 'medical'


class BackgroundCheckViewSet(CompanyScopedViewSet):
    queryset = BackgroundCheck.objects.filter(is_deleted=False)
    serializer_class = BackgroundCheckSerializer
    rbac_module = 'background_checks'

    def get_queryset(self):
        qs = super().get_queryset()
        candidate_id = self.request.query_params.get('candidate_id')
        if candidate_id:
            qs = qs.filter(candidate_id=candidate_id)
        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
        check_type = self.request.query_params.get('check_type')
        if check_type:
            qs = qs.filter(check_type=check_type)
        expiring_within_days = self.request.query_params.get('expiring_within_days')
        if expiring_within_days:
            cutoff = timezone.localdate() + timezone.timedelta(days=int(expiring_within_days))
            qs = qs.filter(expiry_date__isnull=False, expiry_date__lte=cutoff)
        return qs.order_by('-requested_at')

    @action(detail=True, methods=['post'], url_path='request-validation')
    def request_validation(self, request, pk=None):
        """
        Send a Sheer Logic-branded, signable request to a validation body.
        Body: {"validation_body_name": ..., "validation_body_email": ...}
        The body signs + records whether the subject is clean (+ comments);
        the DocuSeal webhook routes the result back to this check.
        """
        from .background_check_service import send_for_validation, ValidationError
        check = self.get_object()
        try:
            result = send_for_validation(
                check,
                validation_body_name=request.data.get('validation_body_name'),
                validation_body_email=request.data.get('validation_body_email'),
                request=request)
        except ValidationError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result)

    def perform_create(self, serializer):
        kwargs = {}
        company_id = request_company_id(self.request)
        if company_id:
            kwargs['company_id'] = serializer.validated_data.get('company_id') or company_id
        kwargs['requested_by'] = request_user_id(self.request)
        serializer.save(**kwargs)

    def perform_destroy(self, instance):
        instance.is_deleted = True
        instance.save(update_fields=['is_deleted', 'updated_at'])

    @action(detail=True, methods=['put', 'patch'])
    def review(self, request, pk=None):
        """Review/complete a check: status must be passed/failed/flagged."""
        check = self.get_object()
        if request.data.get('status') not in ('passed', 'failed', 'flagged'):
            return Response({'error': 'status must be passed, failed, or flagged'}, status=400)
        for field in ('status', 'result_summary', 'clearance_date', 'expiry_date', 'flags', 'notes'):
            if field in request.data:
                setattr(check, field, request.data[field])
        check.completed_at = timezone.now()
        check.reviewed_by = request_user_id(request)
        check.save()
        return Response(self.get_serializer(check).data)


class KpiAssignmentViewSet(CompanyScopedViewSet):
    queryset = KpiAssignment.objects.filter(is_deleted=False)
    serializer_class = KpiAssignmentSerializer
    rbac_module = 'performance'


class PerformanceReviewViewSet(CompanyScopedViewSet):
    queryset = PerformanceReview.objects.filter(is_deleted=False)
    serializer_class = PerformanceReviewSerializer
    rbac_module = 'performance'

    def perform_create(self, serializer):
        kwargs = {}
        company_id = request_company_id(self.request)
        if company_id:
            kwargs['company_id'] = serializer.validated_data.get('company_id') or company_id
        if not serializer.validated_data.get('reviewer_id'):
            kwargs['reviewer_id'] = request_user_id(self.request)
        serializer.save(**kwargs)


class TrainingSessionViewSet(CompanyScopedViewSet):
    queryset = TrainingSession.objects.filter(is_deleted=False)
    serializer_class = TrainingSessionSerializer
    rbac_module = 'training'

    @action(detail=True, methods=['post'])
    def enrol(self, request, pk=None):
        """Bulk-enrol employees. Body: {"employee_ids": [...]}"""
        session = self.get_object()
        created = []
        for emp_id in request.data.get('employee_ids', []):
            obj, was_created = TrainingEnrollment.objects.get_or_create(
                session=session, employee_id=emp_id)
            if was_created:
                created.append(str(emp_id))
        return Response({'enrolled': created}, status=201)


class TrainingEnrollmentViewSet(viewsets.ReadOnlyModelViewSet):
    """Per-employee training history — nests session fields so the
    dashboard's TabTraining gets one flat row per enrollment."""
    serializer_class = TrainingEnrollmentSerializer
    permission_classes = [HasModulePermission]
    rbac_module = 'training'

    def get_queryset(self):
        qs = TrainingEnrollment.objects.select_related('session').filter(
            session__is_deleted=False)
        employee_id = self.request.query_params.get('employee_id')
        if employee_id:
            qs = qs.filter(employee_id=employee_id)
        return qs.order_by('-session__start_date')


class EmployeeOnboardingDocumentViewSet(viewsets.ModelViewSet):
    serializer_class = EmployeeOnboardingDocumentSerializer
    permission_classes = [HasModulePermission]
    rbac_module = 'onboarding'

    def get_queryset(self):
        qs = EmployeeOnboardingDocument.objects.all()
        employee_id = self.request.query_params.get('employee_id')
        if employee_id:
            qs = qs.filter(employee_id=employee_id)
        return qs


class OnboardingSummaryView(views.APIView):
    """
    New hires (last 90 days) + their onboarding-document completion, for
    the dashboard's Onboarding tab. Computed from EmployeeProfile +
    EmployeeOnboardingDocument — there's no single 'onboarding' table.
    """
    permission_classes = [HasModulePermission]
    rbac_module = 'onboarding'

    def get(self, request):
        from apps.core.models import AppUser
        from apps.payroll.models import EmployeeProfile

        company_id = request_company_id(request)
        cutoff = timezone.localdate() - timezone.timedelta(days=90)
        employees = EmployeeProfile.objects.filter(
            is_deleted=False, start_date__gte=cutoff)
        if company_id:
            employees = employees.filter(company_id=company_id)
        employees = list(employees)

        emp_ids = [e.id for e in employees]
        users_by_emp = {u.employee_id: u for u in
                        AppUser.objects.filter(employee_id__in=emp_ids, is_deleted=False)}
        docs_by_emp = {}
        for d in EmployeeOnboardingDocument.objects.filter(employee_id__in=emp_ids):
            docs_by_emp.setdefault(d.employee_id, []).append(d)

        n_doc_types = len(EmployeeOnboardingDocument.DOC_TYPES)
        results = []
        for e in employees:
            docs = docs_by_emp.get(e.id, [])
            verified = sum(1 for d in docs if d.status == 'verified')
            uploaded = sum(1 for d in docs if d.status in ('uploaded', 'verified'))
            u = users_by_emp.get(e.id)
            results.append({
                'id': str(e.id),
                'employee_number': e.employee_number,
                'job_title': e.job_title,
                'department': e.department,
                'start_date': str(e.start_date),
                'employment_status': e.employment_status,
                'user': {
                    'full_name': u.full_name if u else e.job_title,
                    'email': u.email if u else '',
                    'avatar_url': u.avatar_url if u else None,
                },
                'company': {'name': ''},
                'doc_verified': verified,
                'doc_uploaded': uploaded,
                'doc_required': n_doc_types,
                'doc_pct': round(100 * verified / n_doc_types) if n_doc_types else 0,
            })
        return Response(results)


def _one_tap_url(token):
    from django.conf import settings
    base = getattr(settings, 'PUBLIC_API_BASE_URL', 'http://localhost:8000')
    return f'{base}/api/one-tap/{token.token}/'


# ---------------------------------------------------------------------------
# Exit Clearance — structured per-section sign-off
# ---------------------------------------------------------------------------

class ExitClearanceViewSet(viewsets.ModelViewSet):
    """
    CRUD for the structured ExitClearance record tied to an EmployeeExit.
    POST   /api/hr/exits/{exit_id}/clearance/   → create (HR initiates)
    GET    /api/hr/exits/{exit_id}/clearance/   → retrieve
    PATCH  /api/hr/exits/{exit_id}/clearance/{pk}/ → update individual fields
    POST   …/{pk}/sign_section/                 → clear one section and record sign-off
    """
    serializer_class = ExitClearanceSerializer
    permission_classes = [HasModulePermission]
    rbac_module = 'exits'

    def get_queryset(self):
        exit_id = self.kwargs.get('exit_pk') or self.request.query_params.get('exit_id')
        qs = ExitClearance.objects.all()
        if exit_id:
            qs = qs.filter(exit_id=exit_id)
        company_id = request_company_id(self.request)
        if company_id:
            qs = qs.filter(company_id=company_id)
        return qs

    def perform_create(self, serializer):
        exit_id = self.kwargs.get('exit_pk') or self.request.data.get('exit')
        company_id = request_company_id(self.request)
        try:
            exit_ = EmployeeExit.objects.get(id=exit_id)
        except EmployeeExit.DoesNotExist:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({'exit': 'Exit record not found.'})
        serializer.save(exit=exit_, initiated_by=request_user_id(self.request),
                        company_id=company_id, tenant_id=exit_.tenant_id)

    @action(detail=True, methods=['post'])
    def sign_section(self, request, pk=None, **kwargs):
        """
        Body: {"section": "it"|"finance"|"admin"|"hr"|"manager",
               "cleared_by": "Jane Wanjiku", "notes": "optional"}
        Sets <section>_cleared=True, <section>_cleared_by, <section>_cleared_at=now,
        recalculates status.
        """
        clearance = self.get_object()
        section = request.data.get('section', '').lower()
        if section not in ExitClearance.SECTIONS:
            return Response({'error': f'section must be one of {ExitClearance.SECTIONS}'},
                            status=status.HTTP_400_BAD_REQUEST)
        setattr(clearance, f'{section}_cleared', True)
        setattr(clearance, f'{section}_cleared_by',
                request.data.get('cleared_by', ''))
        setattr(clearance, f'{section}_cleared_at', timezone.now())
        if request.data.get('notes'):
            setattr(clearance, f'{section}_notes', request.data['notes'])
        clearance.save()
        clearance.refresh_status()
        ServiceAuditLog.log(
            f'exits.clearance.{section}_signed', request=request,
            object_type='ExitClearance', object_id=str(clearance.id),
            company_id=clearance.company_id,
            metadata={'section': section, 'status': clearance.status})
        return Response(ExitClearanceSerializer(clearance).data)
