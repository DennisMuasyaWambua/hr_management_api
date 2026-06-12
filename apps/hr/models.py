"""
HR domain models (Django-managed, new tables):
allowances/deductions, overtime, reimbursements, statutory rates (versioned),
minimum wage + compliance alerts, disciplinary, exits + clearance, leave
recalls, certificates.

Employee/company references use UUIDs matching Supabase rows (same convention
as apps.payroll managed=False mirrors), so the frontend can join either side.
"""
import uuid

from django.db import models
from django.utils import timezone


class TenantStamped(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    tenant_id = models.UUIDField(null=True, blank=True, db_index=True)
    company_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta:
        abstract = True


# ---------------------------------------------------------------------------
# Allowances & deductions (dynamic, HR-managed)
# ---------------------------------------------------------------------------

class AllowanceType(TenantStamped):
    """HR-defined allowance kind (golf club, fuel, housing, per diem...)."""
    name = models.CharField(max_length=100)
    taxable = models.BooleanField(default=True)
    # Variable allowances (e.g. per diem) reset to zero at month end.
    is_variable = models.BooleanField(default=False)
    default_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'allowance_types'
        unique_together = [('company_id', 'name')]

    def __str__(self):
        return self.name


class EmployeeAllowance(TenantStamped):
    employee_id = models.UUIDField(db_index=True)
    allowance_type = models.ForeignKey(AllowanceType, on_delete=models.CASCADE,
                                       related_name='employee_allowances')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    effective_from = models.DateField(default=timezone.localdate)
    effective_to = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.UUIDField(null=True, blank=True)

    class Meta:
        db_table = 'employee_allowances'

    def active_for(self, year: int, month: int) -> bool:
        import datetime
        first = datetime.date(year, month, 1)
        if not self.is_active or self.effective_from > first.replace(day=28):
            return False
        return self.effective_to is None or self.effective_to >= first


class DeductionType(TenantStamped):
    """Recurring non-statutory deduction kinds (salary penalty, sacco, loan...)."""
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'deduction_types'
        unique_together = [('company_id', 'name')]

    def __str__(self):
        return self.name


class EmployeeDeduction(TenantStamped):
    employee_id = models.UUIDField(db_index=True)
    deduction_type = models.ForeignKey(DeductionType, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    effective_from = models.DateField(default=timezone.localdate)
    effective_to = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    # Links a disciplinary salary penalty to its source record.
    disciplinary_record = models.ForeignKey(
        'DisciplinaryRecord', null=True, blank=True, on_delete=models.SET_NULL)
    created_by = models.UUIDField(null=True, blank=True)

    class Meta:
        db_table = 'employee_deductions'


# ---------------------------------------------------------------------------
# Overtime
# ---------------------------------------------------------------------------

class OvertimeRequest(TenantStamped):
    STATUS = [('pending', 'Pending'), ('approved', 'Approved'),
              ('rejected', 'Rejected')]

    employee_id = models.UUIDField(db_index=True)
    manager_id = models.UUIDField(null=True, blank=True, db_index=True)
    date = models.DateField()
    hours = models.DecimalField(max_digits=5, decimal_places=2)
    rate_multiplier = models.DecimalField(max_digits=4, decimal_places=2, default=1.5)
    reason = models.TextField(blank=True, default='')
    status = models.CharField(max_length=10, choices=STATUS, default='pending')
    decided_by = models.UUIDField(null=True, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'overtime_requests'
        ordering = ['-date']

    def decide(self, decision: str, approver_user_id):
        self.status = decision
        self.decided_by = approver_user_id
        self.decided_at = timezone.now()
        self.save(update_fields=['status', 'decided_by', 'decided_at', 'updated_at'])


# ---------------------------------------------------------------------------
# Reimbursements (separate from allowances per 01-Jun session)
# ---------------------------------------------------------------------------

class Reimbursement(TenantStamped):
    STATUS = [('submitted', 'Submitted'), ('approved', 'Approved'),
              ('rejected', 'Rejected'), ('paid', 'Paid')]

    employee_id = models.UUIDField(db_index=True)
    category = models.CharField(max_length=100)  # per diem top-up, transport...
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.TextField(blank=True, default='')
    receipt_url = models.TextField(blank=True, default='')  # Supabase storage URL
    status = models.CharField(max_length=10, choices=STATUS, default='submitted')
    processed_by = models.UUIDField(null=True, blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    payment_reference = models.CharField(max_length=255, blank=True, default='')

    class Meta:
        db_table = 'reimbursements'
        ordering = ['-created_at']


# ---------------------------------------------------------------------------
# Statutory rates (versioned; super-admin editable; consumed by tax_calculator)
# ---------------------------------------------------------------------------

class StatutoryRate(TenantStamped):
    """
    One versioned row per rate kind. `value` schema by kind:
      paye_bands      {"bands": [{"upto": 24000, "rate": 0.10}, ...], "personal_relief": 2400}
      nssf            {"tier1_max": 7000, "tier2_max": 36000, "rate": 0.06}
      shif (nhif)     {"rate": 0.0275, "minimum": 300}
      housing_levy    {"rate": 0.015}
      vat             {"rate": 0.16}
    Resolution: company-specific row wins over global (company_id null);
    the row effective for the payroll period is chosen by date.
    """
    RATE_KINDS = [('paye_bands', 'PAYE bands'), ('nssf', 'NSSF'),
                  ('shif', 'SHIF/NHIF'), ('housing_levy', 'Housing Levy'),
                  ('vat', 'VAT'), ('helb_min', 'HELB minimum'),
                  ('other', 'Other')]

    kind = models.CharField(max_length=20, choices=RATE_KINDS, db_index=True)
    value = models.JSONField()
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    note = models.CharField(max_length=255, blank=True, default='')
    created_by = models.UUIDField(null=True, blank=True)

    class Meta:
        db_table = 'statutory_rates'
        ordering = ['kind', '-effective_from']

    @classmethod
    def effective(cls, kind: str, on_date, company_id=None):
        from django.db.models import Q
        qs = cls.objects.filter(
            kind=kind, effective_from__lte=on_date,
        ).filter(Q(effective_to__isnull=True) | Q(effective_to__gte=on_date))
        if company_id:
            specific = qs.filter(company_id=company_id).order_by('-effective_from').first()
            if specific:
                return specific
        return qs.filter(company_id__isnull=True).order_by('-effective_from').first()


class MinimumWage(models.Model):
    """Kenyan minimum wage by job category/region (Regulation of Wages orders)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job_category = models.CharField(max_length=150, db_index=True)
    region = models.CharField(max_length=100, default='general')  # cities/municipalities/other
    monthly_amount = models.DecimalField(max_digits=12, decimal_places=2)
    effective_from = models.DateField()
    source = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'minimum_wages'
        ordering = ['job_category', '-effective_from']


class ComplianceAlert(TenantStamped):
    ALERT_TYPES = [('below_minimum_wage', 'Below minimum wage'),
                   ('certificate_expired', 'Certificate expired'),
                   ('other', 'Other')]
    STATUS = [('open', 'Open'), ('acknowledged', 'Acknowledged'),
              ('resolved', 'Resolved')]

    alert_type = models.CharField(max_length=30, choices=ALERT_TYPES)
    employee_id = models.UUIDField(null=True, blank=True, db_index=True)
    payroll_run_id = models.UUIDField(null=True, blank=True)
    details = models.JSONField(default=dict)
    status = models.CharField(max_length=15, choices=STATUS, default='open')
    acknowledged_by = models.UUIDField(null=True, blank=True)

    class Meta:
        db_table = 'compliance_alerts'
        ordering = ['-created_at']


# ---------------------------------------------------------------------------
# Disciplinary (PIP → warning → penalty → termination, per Employment Act)
# ---------------------------------------------------------------------------

class DisciplinaryRecord(TenantStamped):
    KINDS = [('pip', 'Performance Improvement Plan'),
             ('verbal_warning', 'Verbal warning'),
             ('warning_letter', 'Warning letter'),
             ('salary_penalty', 'Salary penalty'),
             ('suspension', 'Suspension'),
             ('termination_recommendation', 'Termination recommendation'),
             ('prior_employer_record', 'Record from previous employer')]
    STATUS = [('open', 'Open'), ('in_progress', 'In progress'),
              ('resolved', 'Resolved'), ('escalated', 'Escalated')]

    employee_id = models.UUIDField(db_index=True)
    kind = models.CharField(max_length=30, choices=KINDS)
    status = models.CharField(max_length=15, choices=STATUS, default='open')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default='')
    document_url = models.TextField(blank=True, default='')
    issued_by = models.UUIDField(null=True, blank=True)
    starts_on = models.DateField(null=True, blank=True)
    ends_on = models.DateField(null=True, blank=True)
    outcome = models.TextField(blank=True, default='')
    # Escalation chain: a warning letter can reference the failed PIP, etc.
    escalated_from = models.ForeignKey('self', null=True, blank=True,
                                       on_delete=models.SET_NULL,
                                       related_name='escalations')

    class Meta:
        db_table = 'disciplinary_records'
        ordering = ['-created_at']


# ---------------------------------------------------------------------------
# Exits (resignation/termination → clearance → final dues)
# ---------------------------------------------------------------------------

class EmployeeExit(TenantStamped):
    KINDS = [('resignation', 'Resignation'), ('termination', 'Termination'),
             ('redundancy', 'Redundancy'), ('contract_end', 'Contract end'),
             ('retirement', 'Retirement')]
    STATUS = [('initiated', 'Initiated'), ('clearance', 'Clearance in progress'),
              ('final_dues', 'Final dues processing'), ('completed', 'Completed'),
              ('cancelled', 'Cancelled')]

    employee_id = models.UUIDField(db_index=True)
    kind = models.CharField(max_length=20, choices=KINDS)
    status = models.CharField(max_length=15, choices=STATUS, default='initiated')
    reason = models.TextField(blank=True, default='')
    notice_date = models.DateField(null=True, blank=True)
    last_working_day = models.DateField(null=True, blank=True)
    initiated_by = models.UUIDField(null=True, blank=True)
    disciplinary_record = models.ForeignKey(DisciplinaryRecord, null=True,
                                            blank=True, on_delete=models.SET_NULL)
    # Final dues snapshot (per Employment Act: notice pay, accrued leave,
    # service pay where applicable, pro-rata salary).
    final_dues = models.JSONField(default=dict, blank=True)
    final_dues_total = models.DecimalField(max_digits=14, decimal_places=2,
                                           null=True, blank=True)
    final_dues_paid_at = models.DateTimeField(null=True, blank=True)
    final_payroll_record_id = models.UUIDField(null=True, blank=True)

    class Meta:
        db_table = 'employee_exits'
        ordering = ['-created_at']


class ExitClearanceItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    exit = models.ForeignKey(EmployeeExit, on_delete=models.CASCADE,
                             related_name='clearance_items')
    item = models.CharField(max_length=255)  # laptop return, gate pass, finance...
    is_cleared = models.BooleanField(default=False)
    cleared_by = models.UUIDField(null=True, blank=True)
    cleared_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'exit_clearance_items'


# ---------------------------------------------------------------------------
# Leave recall
# ---------------------------------------------------------------------------

class LeaveRecall(TenantStamped):
    STATUS = [('pending', 'Pending'), ('approved', 'Approved'),
              ('rejected', 'Rejected')]

    leave_id = models.UUIDField(db_index=True)  # Supabase `leaves` row
    employee_id = models.UUIDField(db_index=True)
    manager_id = models.UUIDField(null=True, blank=True)
    requested_by = models.UUIDField(null=True, blank=True)
    reason = models.TextField(blank=True, default='')
    resume_date = models.DateField()
    days_credited = models.DecimalField(max_digits=5, decimal_places=1,
                                        null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS, default='pending')
    decided_by = models.UUIDField(null=True, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'leave_recalls'
        ordering = ['-created_at']

    def approve(self, approver_user_id):
        self.status = 'approved'
        self.decided_by = approver_user_id
        self.decided_at = timezone.now()
        self.save(update_fields=['status', 'decided_by', 'decided_at', 'updated_at'])

    def reject(self, approver_user_id):
        self.status = 'rejected'
        self.decided_by = approver_user_id
        self.decided_at = timezone.now()
        self.save(update_fields=['status', 'decided_by', 'decided_at', 'updated_at'])


# ---------------------------------------------------------------------------
# Certificates
# ---------------------------------------------------------------------------

class EmployeeCertificate(TenantStamped):
    employee_id = models.UUIDField(db_index=True)
    name = models.CharField(max_length=255)  # police clearance, food handler...
    issuer = models.CharField(max_length=255, blank=True, default='')
    certificate_number = models.CharField(max_length=100, blank=True, default='')
    issue_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True, db_index=True)
    document_url = models.TextField(blank=True, default='')
    alert_days_before = models.PositiveIntegerField(default=30)
    last_alert_sent_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'employee_certificates'
        ordering = ['expiry_date']

    @property
    def is_expired(self):
        return bool(self.expiry_date and self.expiry_date < timezone.localdate())
