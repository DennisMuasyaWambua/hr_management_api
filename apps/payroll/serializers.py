from rest_framework import serializers
from .models import PayrollRun, PayrollRecord, PaymentBatch, Employee, Company


class EmployeePaymentSerializer(serializers.ModelSerializer):
    """Serializer for employee payment method updates"""

    class Meta:
        model = Employee
        fields = [
            'payment_method', 'bank_name', 'bank_account', 'bank_branch',
            'mpesa_number', 'airtel_number'
        ]

    def validate(self, data):
        method = data.get('payment_method')
        if method == 'bank':
            if not data.get('bank_name') or not data.get('bank_account'):
                raise serializers.ValidationError(
                    "Bank name and account number required for bank payment"
                )
        elif method == 'mpesa':
            if not data.get('mpesa_number'):
                raise serializers.ValidationError(
                    "M-Pesa number required for M-Pesa payment"
                )
        elif method == 'airtel':
            if not data.get('airtel_number'):
                raise serializers.ValidationError(
                    "Airtel number required for Airtel Money payment"
                )
        return data


class CompanyPaymentConfigSerializer(serializers.ModelSerializer):
    """Serializer for company payment configuration"""

    class Meta:
        model = Company
        fields = [
            'company_bank_name', 'company_bank_account', 'company_bank_branch',
            'mpesa_paybill_number', 'mpesa_till_number',
            'pesapal_consumer_key', 'pesapal_consumer_secret', 'pesapal_ipn_id'
        ]


class PayrollRecordSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source='employee.user.get_full_name', read_only=True)
    employee_number = serializers.CharField(source='employee.employee_number', read_only=True)

    class Meta:
        model = PayrollRecord
        fields = [
            'id', 'employee', 'employee_name', 'employee_number',
            'basic_salary', 'allowances', 'overtime', 'bonus', 'gross_pay',
            'nssf_employee', 'nssf_employer', 'nhif', 'paye',
            'housing_levy_employee', 'housing_levy_employer', 'helb',
            'other_deductions', 'total_deductions', 'net_pay',
            'payment_status', 'payment_method', 'payment_reference', 'payment_date'
        ]
        read_only_fields = ['id', 'employee_name', 'employee_number']


class PayrollRunListSerializer(serializers.ModelSerializer):
    """List view serializer with summary info"""

    class Meta:
        model = PayrollRun
        fields = [
            'id', 'period_start', 'period_end', 'pay_date', 'status',
            'total_gross', 'total_net', 'employee_count',
            'created_at', 'approved_at'
        ]


class PayrollRunDetailSerializer(serializers.ModelSerializer):
    """Detail view serializer with full breakdown"""
    records = PayrollRecordSerializer(many=True, read_only=True)
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    approved_by_name = serializers.CharField(source='approved_by.get_full_name', read_only=True)

    class Meta:
        model = PayrollRun
        fields = [
            'id', 'period_start', 'period_end', 'pay_date', 'status',
            'total_gross', 'total_net', 'total_paye', 'total_nssf',
            'total_nhif', 'total_housing_levy', 'total_helb',
            'employee_count', 'notes',
            'created_by', 'created_by_name', 'created_at',
            'approved_by', 'approved_by_name', 'approved_at',
            'records'
        ]
        read_only_fields = ['id', 'created_by', 'created_at']


class PayrollRunCreateSerializer(serializers.ModelSerializer):
    """Create a new payroll run"""

    class Meta:
        model = PayrollRun
        fields = ['period_start', 'period_end', 'pay_date', 'notes']

    def validate(self, data):
        # Check for overlapping payroll runs
        request = self.context.get('request')
        if request and hasattr(request.user, 'tenant_id'):
            tenant_id = request.user.tenant_id
            company_id = self.context.get('company_id')

            overlapping = PayrollRun.objects.filter(
                tenant_id=tenant_id,
                company_id=company_id,
                is_deleted=False,
                period_start__lte=data['period_end'],
                period_end__gte=data['period_start']
            ).exists()

            if overlapping:
                raise serializers.ValidationError(
                    "A payroll run already exists for this period"
                )

        return data


class PaymentBatchSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentBatch
        fields = [
            'id', 'payment_method', 'status',
            'total_amount', 'successful_amount', 'failed_amount',
            'record_count', 'successful_count', 'failed_count',
            'started_at', 'completed_at'
        ]


class DisbursePayrollSerializer(serializers.Serializer):
    """Trigger payroll disbursement"""
    record_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        help_text="Specific record IDs to pay. If empty, pays all pending records."
    )
    payment_methods = serializers.ListField(
        child=serializers.ChoiceField(choices=['bank', 'mpesa', 'airtel']),
        required=False,
        help_text="Filter by payment methods. If empty, processes all methods."
    )
