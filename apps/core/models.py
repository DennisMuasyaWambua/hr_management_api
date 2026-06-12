"""
Core models: RBAC, audit trail, notifications, one-tap approval tokens.

All models here are Django-managed (new tables). Mirror SQL for Supabase
(with RLS) lives in sql/sheerlogic_extensions.sql so the frontend can read
them directly where needed.
"""
import secrets
import uuid

from django.db import models
from django.utils import timezone


# ---------------------------------------------------------------------------
# RBAC
# ---------------------------------------------------------------------------

class Role(models.Model):
    """
    A role within a company (or global when company_id is null).
    Lower rank = more authority. The lowest-ranked role in scope is the
    "highest rank" allowed to manage permissions from the frontend.
    """
    SYSTEM_ROLES = [
        ('super_admin', 'Super Admin'),
        ('company_admin', 'Company Admin'),
        ('hr', 'HR'),
        ('manager', 'Manager'),
        ('employee', 'Employee'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company_id = models.UUIDField(null=True, blank=True, db_index=True)  # null = global role
    tenant_id = models.UUIDField(null=True, blank=True, db_index=True)
    slug = models.CharField(max_length=50)
    name = models.CharField(max_length=100)
    rank = models.PositiveIntegerField(default=100)  # 0 = super admin
    is_system = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'rbac_roles'
        unique_together = [('company_id', 'slug')]
        ordering = ['rank']

    def __str__(self):
        return f"{self.name} ({'global' if not self.company_id else self.company_id})"


class Permission(models.Model):
    """A grantable capability, namespaced by module."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    codename = models.CharField(max_length=100, unique=True)  # e.g. payroll.view
    module = models.CharField(max_length=50, db_index=True)   # payroll, leave, attendance...
    description = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'rbac_permissions'
        ordering = ['module', 'codename']

    def __str__(self):
        return self.codename


class RolePermission(models.Model):
    """Grant of a permission to a role; every change is audit-logged."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name='grants')
    permission = models.ForeignKey(Permission, on_delete=models.CASCADE, related_name='grants')
    granted_by = models.UUIDField(null=True, blank=True)  # Supabase user id
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'rbac_role_permissions'
        unique_together = [('role', 'permission')]


class UserRoleAssignment(models.Model):
    """Assignment of a role to a Supabase user within a company."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_id = models.UUIDField(db_index=True)      # Supabase auth user
    company_id = models.UUIDField(db_index=True, null=True, blank=True)
    tenant_id = models.UUIDField(db_index=True, null=True, blank=True)
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name='assignments')
    assigned_by = models.UUIDField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'rbac_user_roles'
        unique_together = [('user_id', 'company_id', 'role')]


class ServiceAuditLog(models.Model):
    """
    Django-side audit trail: who triggered what (payroll runs, approvals,
    permission changes, document generation, disbursements).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    tenant_id = models.UUIDField(null=True, blank=True, db_index=True)
    company_id = models.UUIDField(null=True, blank=True, db_index=True)
    actor_user_id = models.UUIDField(null=True, blank=True)
    actor_label = models.CharField(max_length=255, blank=True, default='')  # e.g. service key, email
    action = models.CharField(max_length=100, db_index=True)  # payroll.submitted, rbac.grant ...
    object_type = models.CharField(max_length=100, blank=True, default='')
    object_id = models.CharField(max_length=100, blank=True, default='')
    metadata = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        db_table = 'service_audit_log'
        ordering = ['-created_at']

    @classmethod
    def log(cls, action, request=None, **kwargs):
        """Convenience helper used across apps."""
        ip = None
        actor_label = kwargs.pop('actor_label', '')
        actor_user_id = kwargs.pop('actor_user_id', None)
        if request is not None:
            ip = request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip() \
                or request.META.get('REMOTE_ADDR')
            actor_user_id = actor_user_id or request.headers.get('X-User-Id') or None
            actor_label = actor_label or request.headers.get('X-User-Email', '')
        return cls.objects.create(
            action=action, ip_address=ip,
            actor_user_id=actor_user_id or None, actor_label=actor_label,
            **kwargs,
        )


# ---------------------------------------------------------------------------
# Notifications (multi-channel: email / SMS / WhatsApp via Africa's Talking)
# ---------------------------------------------------------------------------

class NotificationTemplate(models.Model):
    CHANNEL_CHOICES = [
        ('email', 'Email'),
        ('sms', 'SMS'),
        ('whatsapp', 'WhatsApp'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company_id = models.UUIDField(null=True, blank=True, db_index=True)  # null = global default
    event = models.CharField(max_length=100, db_index=True)  # leave.requested, payroll.pending_approval...
    channel = models.CharField(max_length=10, choices=CHANNEL_CHOICES)
    subject = models.CharField(max_length=255, blank=True, default='')  # email only
    body = models.TextField()  # python str.format placeholders, e.g. {employee_name}
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'notification_templates'
        unique_together = [('company_id', 'event', 'channel')]

    def render(self, context: dict):
        class _Safe(dict):
            def __missing__(self, key):
                return '{' + key + '}'
        ctx = _Safe(context or {})
        return self.subject.format_map(ctx), self.body.format_map(ctx)


class NotificationLog(models.Model):
    STATUS_CHOICES = [
        ('queued', 'Queued'),
        ('sent', 'Sent'),
        ('delivered', 'Delivered'),
        ('failed', 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    tenant_id = models.UUIDField(null=True, blank=True, db_index=True)
    company_id = models.UUIDField(null=True, blank=True, db_index=True)
    source_app = models.CharField(max_length=20, blank=True, default='')  # careers|dashboard|pwa|system
    event = models.CharField(max_length=100, blank=True, default='')
    channel = models.CharField(max_length=10)
    recipient = models.CharField(max_length=255)  # email or E.164 phone
    subject = models.CharField(max_length=255, blank=True, default='')
    body = models.TextField(blank=True, default='')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='queued')
    attempts = models.PositiveIntegerField(default=0)
    provider_message_id = models.CharField(max_length=255, blank=True, default='')
    error = models.TextField(blank=True, default='')
    related_object_type = models.CharField(max_length=100, blank=True, default='')
    related_object_id = models.CharField(max_length=100, blank=True, default='')

    class Meta:
        db_table = 'notification_logs'
        ordering = ['-created_at']


# ---------------------------------------------------------------------------
# One-tap approvals (signed token links sent over SMS/WhatsApp/email)
# ---------------------------------------------------------------------------

class OneTapToken(models.Model):
    ACTION_CHOICES = [
        ('leave.approve', 'Approve leave'),
        ('leave.reject', 'Reject leave'),
        ('leave_recall.approve', 'Approve leave recall'),
        ('overtime.approve', 'Approve overtime'),
        ('overtime.reject', 'Reject overtime'),
        ('payroll.approve', 'Approve payroll run'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    token = models.CharField(max_length=64, unique=True, db_index=True)
    action = models.CharField(max_length=50, choices=ACTION_CHOICES)
    object_id = models.CharField(max_length=100)
    approver_user_id = models.UUIDField()
    company_id = models.UUIDField(null=True, blank=True)
    tenant_id = models.UUIDField(null=True, blank=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'one_tap_tokens'

    @classmethod
    def issue(cls, action, object_id, approver_user_id, ttl_hours=72, **kwargs):
        return cls.objects.create(
            token=secrets.token_urlsafe(32),
            action=action,
            object_id=str(object_id),
            approver_user_id=approver_user_id,
            expires_at=timezone.now() + timezone.timedelta(hours=ttl_hours),
            **kwargs,
        )

    @property
    def is_valid(self):
        return self.used_at is None and self.expires_at > timezone.now()
