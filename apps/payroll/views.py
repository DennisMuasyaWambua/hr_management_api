from rest_framework import viewsets, status, views
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from decimal import Decimal
import logging

from .models import PayrollRun, PayrollRecord, PaymentBatch, EmployeeProfile, Company
from .serializers import (
    PayrollRunListSerializer, PayrollRunDetailSerializer,
    PayrollRunCreateSerializer, PayrollRecordSerializer,
    DisbursePayrollSerializer, PaymentBatchSerializer,
    EmployeePaymentSerializer, EmployeePayrollStatusSerializer,
    DepartmentPaymentStatusSerializer, PaymentHistoryRecordSerializer
)
from .services.tax_calculator import KenyanTaxCalculator
from .services.pesapal import PesaPalService
from .services.intasend import IntaSendService
from .tasks import process_payment_batch, process_ipn_callback

logger = logging.getLogger(__name__)


class PayrollRunViewSet(viewsets.ModelViewSet):
    """
    Payroll Run management endpoints

    Workflow: draft → calculated → approved → processing → completed
    """
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return PayrollRun.objects.filter(
            tenant_id=self.request.user.tenant_id,
            is_deleted=False
        )

    def get_serializer_class(self):
        if self.action == 'list':
            return PayrollRunListSerializer
        if self.action == 'create':
            return PayrollRunCreateSerializer
        return PayrollRunDetailSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if hasattr(self.request.user, 'company_id'):
            context['company_id'] = self.request.user.company_id
        return context

    def perform_create(self, serializer):
        serializer.save(
            tenant_id=self.request.user.tenant_id,
            company_id=self.request.user.company_id,
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

        # Get active employees
        employees = EmployeeProfile.objects.filter(
            tenant_id=request.user.tenant_id,
            company_id=payroll_run.company_id,
            employment_status='active',
            is_deleted=False
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

            for employee in employees:
                # Calculate deductions
                calcs = calculator.calculate_all(
                    gross_pay=employee.salary,
                    helb_deduction=Decimal('0')  # Can be extended
                )

                # Map to Supabase schema fields
                paye = calcs['paye']
                nssf = calcs['nssf_employee']
                nhif = calcs['nhif']
                helb = calcs['helb']
                other_deductions = Decimal('0')
                total_deductions = paye + nssf + nhif + helb + other_deductions
                net_salary = employee.salary - total_deductions

                record = PayrollRecord(
                    tenant_id=request.user.tenant_id,
                    payroll_run=payroll_run,
                    employee=employee,
                    gross_salary=employee.salary,
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
                totals['gross'] += employee.salary
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

        # Group by payment method and create batches
        batches = []
        for method in ['bank', 'mpesa', 'airtel']:
            method_records = records.filter(payment_method=method)
            if method_records.exists():
                batch = PaymentBatch.objects.create(
                    tenant_id=request.user.tenant_id,
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
                    # Queue async processing
                    process_payment_batch.delay(str(batch.id))

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
        return EmployeeProfile.objects.filter(
            tenant_id=self.request.user.tenant_id,
            is_deleted=False
        )

    @action(detail=True, methods=['put', 'patch'])
    def payment_method(self, request, pk=None):
        """Update employee payment method"""
        employee = self.get_object()
        serializer = self.get_serializer(employee, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class EmployeePayrollStatusViewSet(viewsets.GenericViewSet):
    """
    Get employees with their current period payment status.
    Used for the payroll dashboard employee table.
    """
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return EmployeeProfile.objects.filter(
            tenant_id=self.request.user.tenant_id,
            is_deleted=False,
            employment_status='active'
        )

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
            tenant_id=request.user.tenant_id,
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

        # Get user names via raw SQL (since User model is external)
        from django.db import connection
        user_names = {}
        employee_user_ids = list(employees.values_list('user_id', flat=True))
        if employee_user_ids:
            with connection.cursor() as cursor:
                placeholders = ','.join(['%s'] * len(employee_user_ids))
                cursor.execute(
                    f"SELECT id, full_name FROM users WHERE id IN ({placeholders})",
                    employee_user_ids
                )
                for row in cursor.fetchall():
                    user_names[str(row[0])] = row[1]

        # Build response data
        employee_data = []
        department_stats = {}

        for emp in employees:
            emp_id = str(emp.id)
            payment_info = payment_status_map.get(emp_id, {})
            payment_status = payment_info.get('status', 'pending')

            # Add user_full_name attribute for serializer
            emp.user_full_name = user_names.get(str(emp.user_id), emp.job_title)
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
            tenant_id=request.user.tenant_id,
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
