from rest_framework import serializers
from .models import PayrollRun, PayrollRecord, PaymentBatch, EmployeeProfile, Company


class EmployeePaymentSerializer(serializers.ModelSerializer):
    """Serializer for employee payment method updates"""

    class Meta:
        model = EmployeeProfile
        fields = [
            'payment_method', 'bank_name', 'bank_account',
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


class EmployeeProfileSerializer(serializers.ModelSerializer):
    """Basic employee profile serializer"""

    class Meta:
        model = EmployeeProfile
        fields = [
            'id', 'employee_number', 'job_title', 'department',
            'employment_type', 'employment_status', 'salary',
            'payment_method', 'bank_name', 'bank_account',
            'mpesa_number', 'airtel_number'
        ]
        read_only_fields = ['id', 'employee_number']


class EmployeeProfileListSerializer(serializers.ModelSerializer):
    """Full employee profile for dashboard listing."""

    class Meta:
        model = EmployeeProfile
        fields = [
            'id', 'user_id', 'employee_number', 'company_id',
            'department', 'job_title', 'employment_type', 'employment_status',
            'manager_id', 'start_date', 'end_date', 'salary', 'payment_method',
            'bank_name', 'bank_account', 'mpesa_number', 'airtel_number',
            'nssf_number', 'nhif_number', 'kra_pin',
            'id_number', 'date_of_birth', 'gender', 'nationality',
            'next_of_kin_name', 'next_of_kin_phone', 'next_of_kin_relationship',
            'created_at', 'updated_at', 'is_deleted', 'tenant_id',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class CompanySerializer(serializers.ModelSerializer):
    """Full company serializer for dashboard."""

    class Meta:
        model = Company
        fields = [
            'id', 'tenant_id', 'name', 'logo_url', 'industry', 'country',
            'city', 'primary_color', 'contact_email', 'is_active',
            'background_check_required', 'background_check_blocks_hiring',
            'company_bank_name', 'company_bank_account', 'company_bank_branch',
            'mpesa_paybill_number', 'mpesa_till_number',
            'pesapal_consumer_key', 'pesapal_consumer_secret', 'pesapal_ipn_id',
            'pesapal_sandbox', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class PayrollRecordSerializer(serializers.ModelSerializer):
    """Serializer for payroll records matching Supabase schema"""
    employee_number = serializers.CharField(
        source='employee.employee_number', read_only=True
    )
    employee_name = serializers.CharField(
        source='employee.job_title', read_only=True
    )
    total_deductions = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )

    class Meta:
        model = PayrollRecord
        fields = [
            'id', 'employee', 'employee_number', 'employee_name',
            'gross_salary', 'paye', 'nssf', 'nhif', 'helb',
            'other_deductions', 'total_deductions', 'net_salary',
            'payment_method', 'payment_status', 'payment_reference', 'paid_at'
        ]


class MyPayslipSerializer(serializers.ModelSerializer):
    """Employee self-service view of a single payslip (PWA)."""
    total_deductions = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )
    period_month = serializers.IntegerField(source='payroll_run.period_month', read_only=True)
    period_year = serializers.IntegerField(source='payroll_run.period_year', read_only=True)
    run_status = serializers.CharField(source='payroll_run.status', read_only=True)

    class Meta:
        model = PayrollRecord
        fields = [
            'id', 'gross_salary', 'paye', 'nssf', 'nhif', 'helb',
            'other_deductions', 'total_deductions', 'net_salary',
            'payment_method', 'payment_status', 'paid_at', 'created_at',
            'period_month', 'period_year', 'run_status',
        ]
        read_only_fields = ['id', 'employee_number', 'employee_name', 'total_deductions']


class PayrollRunListSerializer(serializers.ModelSerializer):
    """List view serializer with summary info"""
    period_display = serializers.CharField(read_only=True)
    record_count = serializers.SerializerMethodField()

    class Meta:
        model = PayrollRun
        fields = [
            'id', 'period_month', 'period_year', 'period_display',
            'status', 'total_gross', 'total_deductions', 'total_net',
            'record_count', 'created_at', 'completed_at'
        ]

    def get_record_count(self, obj):
        return obj.records.count()


class PayrollRunDetailSerializer(serializers.ModelSerializer):
    """Detail view serializer with full breakdown"""
    records = PayrollRecordSerializer(many=True, read_only=True)
    period_display = serializers.CharField(read_only=True)

    class Meta:
        model = PayrollRun
        fields = [
            'id', 'period_month', 'period_year', 'period_display',
            'status', 'total_gross', 'total_deductions', 'total_net',
            'run_by', 'created_at', 'completed_at', 'records'
        ]
        read_only_fields = ['id', 'created_at']


class PayrollRunCreateSerializer(serializers.ModelSerializer):
    """Create a new payroll run"""

    class Meta:
        model = PayrollRun
        fields = ['period_month', 'period_year']

    def validate_period_month(self, value):
        if not 1 <= value <= 12:
            raise serializers.ValidationError("Month must be between 1 and 12")
        return value

    def validate_period_year(self, value):
        if value < 2000 or value > 2100:
            raise serializers.ValidationError("Year must be between 2000 and 2100")
        return value

    def validate(self, data):
        # Check for existing payroll run for same period
        request = self.context.get('request')
        company_id = self.context.get('company_id')

        if company_id:
            existing = PayrollRun.objects.filter(
                company_id=company_id,
                period_month=data['period_month'],
                period_year=data['period_year'],
                is_deleted=False
            ).exists()

            if existing:
                raise serializers.ValidationError(
                    f"A payroll run already exists for {data['period_month']}/{data['period_year']}"
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


class PayrollCalculateSerializer(serializers.Serializer):
    """Request to calculate payroll for employees"""
    employee_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        help_text="Specific employee IDs. If empty, includes all active employees."
    )


class EmployeePayrollStatusSerializer(serializers.Serializer):
    """Employee with current period payment status"""
    id = serializers.UUIDField()
    employee_id = serializers.UUIDField(source='id')
    employee_name = serializers.SerializerMethodField()
    employee_number = serializers.CharField()
    department = serializers.CharField(allow_null=True)
    salary = serializers.DecimalField(max_digits=12, decimal_places=2)
    payment_status = serializers.CharField()
    payment_method = serializers.CharField()
    last_paid_at = serializers.DateTimeField(allow_null=True)

    def get_employee_name(self, obj):
        # Get full_name from the related user
        if hasattr(obj, 'user_full_name'):
            return obj.user_full_name
        return obj.job_title  # Fallback


class DepartmentPaymentStatusSerializer(serializers.Serializer):
    """Department payment status aggregation"""
    department = serializers.CharField()
    total_employees = serializers.IntegerField()
    paid_count = serializers.IntegerField()
    pending_count = serializers.IntegerField()
    status = serializers.CharField()


class PaymentHistoryRecordSerializer(serializers.Serializer):
    """Historical payment record"""
    id = serializers.UUIDField()
    employee_id = serializers.UUIDField()
    employee_name = serializers.CharField()
    employee_number = serializers.CharField()
    department = serializers.CharField(allow_null=True)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    payment_method = serializers.CharField()
    payment_date = serializers.DateTimeField(allow_null=True)
    reference = serializers.CharField(allow_null=True)
    status = serializers.CharField()
    period_month = serializers.IntegerField()
    period_year = serializers.IntegerField()
