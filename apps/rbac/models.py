"""
Part B0 — multi-tenant RBAC data model (built fresh per the spec).

These tables are independent of the legacy ``apps.core`` role helpers and are
prefixed ``orgrbac_`` to avoid any collision. Everything in Part B (enforcement
middleware, company-admin UI, organigram, tenant-isolation tests) is built on
top of these six entities.
"""
import uuid

from django.db import models


class Organization(models.Model):
    INTERNAL = 'INTERNAL'
    CLIENT = 'CLIENT'
    TYPE_CHOICES = [(INTERNAL, 'Internal'), (CLIENT, 'Client')]

    ACTIVE = 'ACTIVE'
    SUSPENDED = 'SUSPENDED'
    STATUS_CHOICES = [(ACTIVE, 'Active'), (SUSPENDED, 'Suspended')]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=CLIENT)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=ACTIVE)

    # Partner-company metadata captured by the company-admin UI (B2).
    industry = models.CharField(max_length=120, blank=True, default='')
    country = models.CharField(max_length=120, blank=True, default='')
    logo_url = models.TextField(blank=True, default='')

    # Optional bridge to the legacy payroll Company so existing employee/payroll
    # rows can be associated with an Organization for tenant scoping.
    company_id = models.UUIDField(null=True, blank=True, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'orgrbac_organizations'
        ordering = ['name']

    def __str__(self):
        return f'{self.name} ({self.type})'


class Permission(models.Model):
    """A single ``resource.action`` capability, e.g. ``payroll.approve``."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    resource = models.CharField(max_length=80)
    action = models.CharField(max_length=40)
    description = models.CharField(max_length=255, blank=True, default='')

    class Meta:
        db_table = 'orgrbac_permissions'
        unique_together = [('resource', 'action')]
        ordering = ['resource', 'action']

    @property
    def code(self):
        return f'{self.resource}.{self.action}'

    def __str__(self):
        return self.code


class Role(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120)
    description = models.CharField(max_length=255, blank=True, default='')
    # NULL organization => system-wide template role.
    organization = models.ForeignKey(
        Organization, null=True, blank=True,
        on_delete=models.CASCADE, related_name='roles',
    )
    is_system_role = models.BooleanField(default=False)
    permissions = models.ManyToManyField(
        Permission, through='RolePermission', related_name='roles',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'orgrbac_roles'
        ordering = ['name']
        # Postgres treats NULLs as distinct, so this only constrains
        # company-scoped roles; system roles are kept unique via get_or_create
        # in the seed command.
        unique_together = [('organization', 'name')]

    def __str__(self):
        scope = self.organization.name if self.organization_id else 'system'
        return f'{self.name} [{scope}]'


class RolePermission(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    role = models.ForeignKey(
        Role, on_delete=models.CASCADE, related_name='role_permissions',
    )
    permission = models.ForeignKey(
        Permission, on_delete=models.CASCADE, related_name='role_permissions',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'orgrbac_role_permissions'
        unique_together = [('role', 'permission')]


class UserRole(models.Model):
    """Grants a user a role within an organization. A user may hold many."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_id = models.UUIDField(db_index=True)
    role = models.ForeignKey(
        Role, on_delete=models.CASCADE, related_name='user_roles',
    )
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name='user_roles',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'orgrbac_user_roles'
        unique_together = [('user_id', 'role', 'organization')]
        indexes = [models.Index(fields=['user_id', 'organization'])]


class OrganigramNode(models.Model):
    """A position in a company's org chart: a role with an optional title
    override and an optionally-assigned user, linked to a parent node."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name='organigram_nodes',
    )
    role = models.ForeignKey(
        Role, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='organigram_nodes',
    )
    parent_node = models.ForeignKey(
        'self', null=True, blank=True,
        on_delete=models.CASCADE, related_name='children',
    )
    title = models.CharField(max_length=255, blank=True, default='')
    # User occupying this position (assigned from the organigram / team view).
    user_id = models.UUIDField(null=True, blank=True, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'orgrbac_organigram_nodes'
        ordering = ['created_at']
