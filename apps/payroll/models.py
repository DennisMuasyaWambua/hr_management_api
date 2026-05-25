from django.db import models
from django.contrib.auth import get_user_model
import uuid

User = get_user_model()


class Company(models.Model):
    """
    Maps to Supabase 'companies' table.
    Note: Payment config fields (pesapal_*) added via SQL migration.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_deleted = models.BooleanField(default=False)
    tenant_id = models.UUIDField(db_index=True)

    # Core company fields (match Supabase)
    name = models.CharField(max_length=255)
    logo_url = models.TextField(null=True, blank=True)
    industry = models.TextField(null=True, blank=True)
    country = models.CharField(max_length=100, default='Kenya')
    city = models.TextField(null=True, blank=True)
    primary_color = models.TextField(null=True, blank=True)
    contact_email = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)

    # Background check settings (match Supabase)
    background_check_required = models.BooleanField(default=False)
    background_check_blocks_hiring = models.BooleanField(default=False)

    # Payment config fields (add to Supabase via migration)
    company_bank_name = models.CharField(max_length=100, null=True, blank=True)
    company_bank_account = models.CharField(max_length=50, null=True, blank=True)
    company_bank_branch = models.CharField(max_length=100, null=True, blank=True)
    mpesa_paybill_number = models.CharField(max_length=20, null=True, blank=True)
    mpesa_till_number = models.CharField(max_length=20, null=True, blank=True)

    # PesaPal integration
    pesapal_consumer_key = models.CharField(max_length=255, null=True, blank=True)
    pesapal_consumer_secret = models.CharField(max_length=255, null=True, blank=True)
    pesapal_ipn_id = models.CharField(max_length=100, null=True, blank=True)
    pesapal_sandbox = models.BooleanField(default=True)

    class Meta:
        db_table = 'companies'
        managed = False  # Don't let Django manage this table
        verbose_name_plural = 'Companies'

    def __str__(self):
        return self.name


class EmployeeProfile(models.Model):
    """
    Maps to Supabase 'employee_profiles' table.
    Renamed from Employee to match Supabase naming.
    """
    EMPLOYMENT_TYPE_CHOICES = [
        ('full_time', 'Full Time'),
        ('part_time', 'Part Time'),
        ('contract', 'Contract'),
        ('intern', 'Intern'),
    ]

    EMPLOYMENT_STATUS_CHOICES = [
        ('active', 'Active'),
        ('on_leave', 'On Leave'),
        ('suspended', 'Suspended'),
        ('terminated', 'Terminated'),
        ('resigned', 'Resigned'),
    ]

    PAYMENT_METHOD_CHOICES = [
        ('bank', 'Bank Transfer'),
        ('mpesa', 'M-Pesa'),
        ('airtel', 'Airtel Money'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_deleted = models.BooleanField(default=False)
    tenant_id = models.UUIDField(db_index=True)

    # Core employee fields
    user_id = models.UUIDField()  # FK to auth.users, not Django User
    employee_number = models.CharField(max_length=50)
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, db_column='company_id'
    )
    department = models.TextField(null=True, blank=True)
    job_title = models.CharField(max_length=255)
    employment_type = models.CharField(max_length=20, choices=EMPLOYMENT_TYPE_CHOICES)
    employment_status = models.CharField(
        max_length=20, choices=EMPLOYMENT_STATUS_CHOICES, default='active'
    )
    manager_id = models.UUIDField(null=True, blank=True)  # FK to users

    # Employment dates
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    contract_duration_months = models.IntegerField(null=True, blank=True)

    # Salary & Payment
    salary = models.DecimalField(max_digits=12, decimal_places=2)
    payment_method = models.CharField(max_length=10, choices=PAYMENT_METHOD_CHOICES)
    bank_name = models.TextField(null=True, blank=True)
    bank_account = models.TextField(null=True, blank=True)
    mpesa_number = models.TextField(null=True, blank=True)
    airtel_number = models.TextField(null=True, blank=True)

    # Statutory numbers
    nssf_number = models.TextField(null=True, blank=True)
    nhif_number = models.TextField(null=True, blank=True)
    kra_pin = models.TextField(null=True, blank=True)

    # Personal info
    id_number = models.TextField(null=True, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.TextField(null=True, blank=True)
    nationality = models.TextField(null=True, blank=True)

    # Next of kin
    next_of_kin_name = models.TextField(null=True, blank=True)
    next_of_kin_phone = models.TextField(null=True, blank=True)
    next_of_kin_relationship = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'employee_profiles'
        managed = False  # Don't let Django manage this table

    def __str__(self):
        return f"{self.employee_number} - {self.job_title}"


# Alias for backward compatibility
Employee = EmployeeProfile


class PayrollRun(models.Model):
    """
    Maps to Supabase 'payroll_runs' table.
    Uses period_month/period_year instead of date range.
    """
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('calculated', 'Calculated'),
        ('approved', 'Approved'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_deleted = models.BooleanField(default=False)
    tenant_id = models.UUIDField(db_index=True)

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, db_column='company_id'
    )

    # Period (Supabase uses month/year)
    period_month = models.IntegerField()  # 1-12
    period_year = models.IntegerField()

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')

    # Totals
    total_gross = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_deductions = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_net = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    # Workflow
    run_by = models.UUIDField()  # FK to users table
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'payroll_runs'
        managed = False
        ordering = ['-period_year', '-period_month']

    def __str__(self):
        return f"Payroll {self.period_month}/{self.period_year} ({self.status})"

    @property
    def period_display(self):
        """Human-readable period string"""
        import calendar
        month_name = calendar.month_name[self.period_month]
        return f"{month_name} {self.period_year}"


class PayrollRecord(models.Model):
    """
    Maps to Supabase 'payroll_records' table.
    Simplified structure matching Supabase schema.
    """
    PAYMENT_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('paid', 'Paid'),
        ('failed', 'Failed'),
    ]

    PAYMENT_METHOD_CHOICES = [
        ('bank', 'Bank Transfer'),
        ('mpesa', 'M-Pesa'),
        ('airtel', 'Airtel Money'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_deleted = models.BooleanField(default=False)
    tenant_id = models.UUIDField(db_index=True)

    payroll_run = models.ForeignKey(
        PayrollRun, on_delete=models.CASCADE,
        related_name='records', db_column='payroll_run_id'
    )
    employee = models.ForeignKey(
        EmployeeProfile, on_delete=models.CASCADE, db_column='employee_id'
    )

    # Salary breakdown (matches Supabase schema)
    gross_salary = models.DecimalField(max_digits=12, decimal_places=2)

    # Deductions
    paye = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    nssf = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    nhif = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    helb = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    other_deductions = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # Net
    net_salary = models.DecimalField(max_digits=12, decimal_places=2)

    # Payment tracking
    payment_method = models.CharField(max_length=10, choices=PAYMENT_METHOD_CHOICES)
    payment_status = models.CharField(
        max_length=20, choices=PAYMENT_STATUS_CHOICES, default='pending'
    )
    payment_reference = models.TextField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'payroll_records'
        managed = False

    def __str__(self):
        return f"{self.employee.employee_number} - {self.payroll_run.period_display}"

    @property
    def total_deductions(self):
        """Calculate total deductions"""
        return self.paye + self.nssf + self.nhif + self.helb + self.other_deductions


class PaymentBatch(models.Model):
    """
    Payment batch for bulk processing.
    This table may need to be created in Supabase.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('partial', 'Partial'),
        ('failed', 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    tenant_id = models.UUIDField(db_index=True)

    payroll_run = models.ForeignKey(
        PayrollRun, on_delete=models.CASCADE,
        related_name='payment_batches', db_column='payroll_run_id'
    )

    payment_method = models.CharField(max_length=10)
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

    class Meta:
        db_table = 'payment_batches'
        managed = False  # Create in Supabase first

    def __str__(self):
        return f"Batch {self.payment_method} - {self.status}"
