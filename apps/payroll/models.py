from django.db import models
from django.contrib.auth import get_user_model
import uuid

User = get_user_model()


class Company(models.Model):
    """Tenant/Company model"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    tenant_id = models.UUIDField(db_index=True)
    name = models.CharField(max_length=255)

    # Company payment accounts
    company_bank_name = models.CharField(max_length=100, null=True, blank=True)
    company_bank_account = models.CharField(max_length=50, null=True, blank=True)
    company_bank_branch = models.CharField(max_length=100, null=True, blank=True)
    mpesa_paybill_number = models.CharField(max_length=20, null=True, blank=True)
    mpesa_till_number = models.CharField(max_length=20, null=True, blank=True)

    # PesaPal integration
    pesapal_consumer_key = models.CharField(max_length=255, null=True, blank=True)
    pesapal_consumer_secret = models.CharField(max_length=255, null=True, blank=True)
    pesapal_ipn_id = models.CharField(max_length=100, null=True, blank=True)
    pesapal_sandbox = models.BooleanField(default=True, help_text="Use PesaPal sandbox environment")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'Companies'

    def __str__(self):
        return self.name


class Employee(models.Model):
    """Employee model with payment preferences"""
    PAYMENT_METHODS = [
        ('bank', 'Bank Transfer'),
        ('mpesa', 'M-Pesa'),
        ('airtel', 'Airtel Money'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    tenant_id = models.UUIDField(db_index=True)
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    employee_number = models.CharField(max_length=50)

    # Salary
    salary = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # Payment method preferences
    payment_method = models.CharField(max_length=10, choices=PAYMENT_METHODS, default='bank')
    bank_name = models.CharField(max_length=100, null=True, blank=True)
    bank_account = models.CharField(max_length=50, null=True, blank=True)
    bank_branch = models.CharField(max_length=100, null=True, blank=True)
    mpesa_number = models.CharField(max_length=15, null=True, blank=True)
    airtel_number = models.CharField(max_length=15, null=True, blank=True)

    # Statutory numbers
    nssf_number = models.CharField(max_length=50, null=True, blank=True)
    nhif_number = models.CharField(max_length=50, null=True, blank=True)
    kra_pin = models.CharField(max_length=20, null=True, blank=True)
    helb_number = models.CharField(max_length=50, null=True, blank=True)
    helb_deduction = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Employment details
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, default='active')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_deleted = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.employee_number} - {self.user.get_full_name()}"


class PayrollRun(models.Model):
    """Monthly payroll run"""
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('calculated', 'Calculated'),
        ('approved', 'Approved'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    tenant_id = models.UUIDField(db_index=True)
    company = models.ForeignKey(Company, on_delete=models.CASCADE)

    period_start = models.DateField()
    period_end = models.DateField()
    pay_date = models.DateField()

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')

    # Totals (calculated)
    total_gross = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_net = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_paye = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_nssf = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_nhif = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_housing_levy = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_helb = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    employee_count = models.IntegerField(default=0)

    # Workflow
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name='created_payroll_runs'
    )
    approved_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_payroll_runs'
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    notes = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_deleted = models.BooleanField(default=False)

    class Meta:
        ordering = ['-period_start']
        unique_together = ['tenant_id', 'company', 'period_start', 'period_end']

    def __str__(self):
        return f"Payroll {self.period_start} - {self.period_end} ({self.status})"


class PayrollRecord(models.Model):
    """Individual employee payroll record within a run"""
    PAYMENT_STATUS = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('paid', 'Paid'),
        ('failed', 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    tenant_id = models.UUIDField(db_index=True)
    payroll_run = models.ForeignKey(PayrollRun, on_delete=models.CASCADE, related_name='records')
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)

    # Earnings
    basic_salary = models.DecimalField(max_digits=12, decimal_places=2)
    allowances = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    overtime = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    bonus = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    gross_pay = models.DecimalField(max_digits=12, decimal_places=2)

    # Statutory deductions (Kenya)
    nssf_employee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    nssf_employer = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    nhif = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    paye = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    housing_levy_employee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    housing_levy_employer = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    helb = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Other deductions
    other_deductions = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_deductions = models.DecimalField(max_digits=12, decimal_places=2)

    # Net
    net_pay = models.DecimalField(max_digits=12, decimal_places=2)

    # Payment tracking
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS, default='pending')
    payment_method = models.CharField(max_length=10)
    payment_reference = models.CharField(max_length=100, null=True, blank=True)
    payment_date = models.DateTimeField(null=True, blank=True)
    payment_error = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.employee.employee_number} - {self.payroll_run.period_start}"


class PaymentBatch(models.Model):
    """Batch of payments for bulk processing"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('partial', 'Partial'),
        ('failed', 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    tenant_id = models.UUIDField(db_index=True)
    payroll_run = models.ForeignKey(PayrollRun, on_delete=models.CASCADE, related_name='payment_batches')

    payment_method = models.CharField(max_length=10)  # bank, mpesa, airtel
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    total_amount = models.DecimalField(max_digits=14, decimal_places=2)
    successful_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    failed_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    record_count = models.IntegerField(default=0)
    successful_count = models.IntegerField(default=0)
    failed_count = models.IntegerField(default=0)

    # PesaPal tracking
    pesapal_order_tracking_id = models.CharField(max_length=100, null=True, blank=True)
    pesapal_merchant_reference = models.CharField(max_length=100, null=True, blank=True)

    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Batch {self.payment_method} - {self.status}"
