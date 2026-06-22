"""
Payroll approval workflow models (new, Django-managed tables).

References to payroll_runs/users use UUIDs (not FK constraints) because those
tables are unmanaged Supabase mirrors — same convention as apps.hr.

Lifecycle implemented on top of the existing PayrollRun.status:
    draft → calculated → pending_approval → approved → processing → completed/paid
The two new states (pending_approval, paid) are additive; every existing
transition keeps working.
"""
import uuid

from django.db import models
from django.utils import timezone


class ApproverConfig(models.Model):
    """Per-company approval quorum: require M approvals of N approvers."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    tenant_id = models.UUIDField(null=True, blank=True, db_index=True)
    company_id = models.UUIDField(unique=True, db_index=True)
    required_approvals = models.PositiveIntegerField(default=2)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'payroll_approver_configs'

    def __str__(self):
        return f'{self.company_id}: {self.required_approvals} of {self.approvers.count()}'


class PayrollApprover(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    config = models.ForeignKey(ApproverConfig, on_delete=models.CASCADE,
                               related_name='approvers')
    user_id = models.UUIDField()
    name = models.CharField(max_length=255, blank=True, default='')
    email = models.EmailField()
    phone = models.CharField(max_length=20, blank=True, default='')
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'payroll_approvers'
        unique_together = [('config', 'user_id')]
        ordering = ['order']


class PayrollApproval(models.Model):
    """One approver's signed decision on one payroll run."""
    DECISIONS = [('approved', 'Approved'), ('rejected', 'Rejected')]
    VIA = [('dashboard', 'Dashboard'), ('one_tap', 'One-tap link'),
           ('docuseal', 'DocuSeal signature')]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    tenant_id = models.UUIDField(null=True, blank=True, db_index=True)
    company_id = models.UUIDField(null=True, blank=True, db_index=True)
    payroll_run_id = models.UUIDField(db_index=True)
    approver_user_id = models.UUIDField()
    decision = models.CharField(max_length=10, choices=DECISIONS)
    via = models.CharField(max_length=10, choices=VIA, default='dashboard')
    comment = models.TextField(blank=True, default='')
    docuseal_submitter_slug = models.CharField(max_length=100, blank=True, default='')
    # Hand-drawn signature captured on the approval page (base64 PNG data URL).
    signature_image = models.TextField(blank=True, default='')
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    signed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'payroll_approvals'
        unique_together = [('payroll_run_id', 'approver_user_id')]
        ordering = ['-signed_at']


class PayrollDocument(models.Model):
    """Generated payroll artifacts: PDF/Excel/payslips, with tamper evidence."""
    DOC_TYPES = [('payroll_pdf', 'Payroll PDF'), ('payroll_excel', 'Payroll Excel'),
                 ('payslip_pdf', 'Payslip PDF'), ('signed_pdf', 'Signed PDF')]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    tenant_id = models.UUIDField(null=True, blank=True, db_index=True)
    company_id = models.UUIDField(null=True, blank=True, db_index=True)
    payroll_run_id = models.UUIDField(db_index=True)
    payroll_record_id = models.UUIDField(null=True, blank=True)  # payslips
    doc_type = models.CharField(max_length=20, choices=DOC_TYPES)
    file = models.FileField(upload_to='payroll_documents/%Y/%m/')
    sha256 = models.CharField(max_length=64)
    password_protected = models.BooleanField(default=False)
    docuseal_template_id = models.CharField(max_length=100, blank=True, default='')
    docuseal_submission_id = models.CharField(max_length=100, blank=True, default='')
    is_signed = models.BooleanField(default=False)
    is_locked = models.BooleanField(default=False)  # locked once run is paid
    generated_by = models.UUIDField(null=True, blank=True)

    class Meta:
        db_table = 'payroll_documents'
        ordering = ['-created_at']
