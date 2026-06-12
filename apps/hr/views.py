"""
HR API: allowances, deductions, overtime, reimbursements, statutory rates,
minimum wage compliance, disciplinary, exits, leave recalls, certificates.
"""
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.models import OneTapToken, ServiceAuditLog
from apps.core.permissions import (HasModulePermission, IsHighestRank,
                                   request_company_id, request_user_id)
from apps.core.services import notifications as notif

from .models import (AllowanceType, ComplianceAlert, DeductionType,
                     DisciplinaryRecord, EmployeeAllowance, EmployeeCertificate,
                     EmployeeDeduction, EmployeeExit, ExitClearanceItem,
                     LeaveRecall, MinimumWage, OvertimeRequest, Reimbursement,
                     StatutoryRate)
from .serializers import (AllowanceTypeSerializer, ComplianceAlertSerializer,
                          DeductionTypeSerializer, DisciplinaryRecordSerializer,
                          EmployeeAllowanceSerializer,
                          EmployeeCertificateSerializer,
                          EmployeeDeductionSerializer, EmployeeExitSerializer,
                          ExitClearanceItemSerializer, LeaveRecallSerializer,
                          MinimumWageSerializer, OvertimeRequestSerializer,
                          ReimbursementSerializer, StatutoryRateSerializer)


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


def _one_tap_url(token):
    from django.conf import settings
    base = getattr(settings, 'PUBLIC_API_BASE_URL', 'http://localhost:8000')
    return f'{base}/api/one-tap/{token.token}/'
