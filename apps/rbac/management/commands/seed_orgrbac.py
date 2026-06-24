"""
Seed the Part B0 RBAC schema: all permissions, the Sheer Logic INTERNAL
organization, every system role template, and sensible default role→permission
grants.

Idempotent — safe to run repeatedly (uses get_or_create). Run with:

    python manage.py seed_orgrbac
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.rbac.models import (
    Organization, Permission, Role, RolePermission,
)

# --- All permissions (resource.action), exactly per the spec -------------
PERMISSIONS = [
    ('candidate', 'view'), ('candidate', 'edit'), ('candidate', 'delete'),
    ('vacancy', 'create'), ('vacancy', 'edit'), ('vacancy', 'publish'),
    ('vacancy', 'close'), ('vacancy', 'archive'),
    ('interview', 'schedule'), ('interview', 'score'), ('interview', 'view'),
    ('offer', 'create'), ('offer', 'approve'), ('offer', 'view'),
    ('employee', 'view'), ('employee', 'edit'), ('employee', 'create'),
    ('payroll', 'view'), ('payroll', 'run'), ('payroll', 'approve'),
    ('payroll', 'export'),
    ('report', 'view'), ('report', 'export'),
    ('organization', 'manage'),
    ('roles', 'manage'),
    ('permissions', 'manage'),
    ('onboarding', 'manage'),
    ('document', 'upload'), ('document', 'verify'),
]

ALL = {f'{r}.{a}' for r, a in PERMISSIONS}

# --- System role templates, grouped (org=None, is_system_role=True) -------
# group -> {role_slug: (description, set_of_permission_codes)}
SYSTEM_ROLES = {
    'Sheer Logic Internal': {
        'super_admin': ('Full system access', ALL),
        'hr_director': ('Heads HR; full HR + payroll + reports', {
            'employee.view', 'employee.edit', 'employee.create',
            'payroll.view', 'payroll.run', 'payroll.approve', 'payroll.export',
            'report.view', 'report.export', 'onboarding.manage',
            'offer.create', 'offer.approve', 'offer.view',
            'document.upload', 'document.verify', 'roles.manage',
        }),
        'senior_recruiter': ('Senior recruitment ownership', {
            'candidate.view', 'candidate.edit', 'candidate.delete',
            'vacancy.create', 'vacancy.edit', 'vacancy.publish',
            'vacancy.close', 'vacancy.archive',
            'interview.schedule', 'interview.score', 'interview.view',
            'offer.create', 'offer.view', 'report.view',
        }),
        'recruiter': ('Day-to-day recruitment', {
            'candidate.view', 'candidate.edit',
            'vacancy.create', 'vacancy.edit', 'vacancy.publish',
            'interview.schedule', 'interview.score', 'interview.view',
            'offer.view',
        }),
        'talent_sourcer': ('Sources and screens candidates', {
            'candidate.view', 'candidate.edit', 'interview.view',
        }),
        'hr_operations_officer': ('HR ops, onboarding, documents', {
            'employee.view', 'employee.edit', 'employee.create',
            'onboarding.manage', 'document.upload', 'document.verify',
            'report.view',
        }),
    },
    'Client Company': {
        'client_admin': ('Client company administrator', {
            'organization.manage', 'roles.manage', 'permissions.manage',
            'employee.view', 'employee.edit', 'employee.create',
            'payroll.view', 'report.view', 'report.export',
            'onboarding.manage', 'document.upload', 'document.verify',
            'offer.view', 'offer.approve',
        }),
        'hiring_manager': ('Owns reqs and hiring decisions', {
            'candidate.view', 'vacancy.create', 'vacancy.edit',
            'interview.schedule', 'interview.score', 'interview.view',
            'offer.create', 'offer.view',
        }),
        'hr_manager': ('Client HR manager', {
            'employee.view', 'employee.edit', 'employee.create',
            'onboarding.manage', 'payroll.view', 'report.view',
            'document.upload', 'document.verify',
        }),
        'interview_panel_member': ('Scores interviews only', {
            'interview.score', 'interview.view', 'candidate.view',
        }),
        'finance_approver': ('Approves payroll/payments', {
            'payroll.view', 'payroll.approve', 'report.view',
        }),
        'department_head': ('Department oversight', {
            'employee.view', 'report.view', 'interview.view', 'offer.view',
        }),
    },
    'Candidate': {
        'candidate': ('External job candidate', set()),
        'contractor': ('External contractor', {'document.upload'}),
    },
    'Employee HR Module': {
        'employee': ('Self-service employee', {'employee.view'}),
        'supervisor': ('Line manager', {
            'employee.view', 'report.view', 'interview.view',
        }),
        'hr_business_partner': ('Embedded HR partner', {
            'employee.view', 'employee.edit', 'onboarding.manage',
            'report.view', 'document.upload', 'document.verify',
        }),
        'payroll_officer': ('Runs payroll', {
            'payroll.view', 'payroll.run', 'payroll.export',
            'report.view', 'report.export', 'employee.view',
        }),
        'finance_manager': ('Finance oversight of payroll', {
            'payroll.view', 'payroll.approve', 'payroll.export',
            'report.view', 'report.export',
        }),
    },
}


class Command(BaseCommand):
    help = 'Seed Part B0 RBAC permissions, internal org, and system roles.'

    @transaction.atomic
    def handle(self, *args, **options):
        # 1. Permissions
        perm_by_code = {}
        for resource, action in PERMISSIONS:
            perm, _ = Permission.objects.get_or_create(
                resource=resource, action=action,
                defaults={'description': f'Can {action} {resource}'},
            )
            perm_by_code[perm.code] = perm
        self.stdout.write(self.style.SUCCESS(
            f'Permissions: {len(perm_by_code)}'))

        # 2. Sheer Logic internal organization
        internal, _ = Organization.objects.get_or_create(
            name='Sheer Logic',
            defaults={'type': Organization.INTERNAL, 'status': Organization.ACTIVE,
                      'industry': 'Recruitment & Staffing', 'country': 'Kenya'},
        )
        # Ensure type stays INTERNAL even if a row pre-existed.
        if internal.type != Organization.INTERNAL:
            internal.type = Organization.INTERNAL
            internal.save(update_fields=['type'])
        self.stdout.write(self.style.SUCCESS(f'Internal org: {internal.name}'))

        # 3. System roles + default permission grants
        role_count = 0
        grant_count = 0
        for group, roles in SYSTEM_ROLES.items():
            for slug, (desc, codes) in roles.items():
                role, _ = Role.objects.get_or_create(
                    organization=None, name=slug,
                    defaults={'description': desc, 'is_system_role': True},
                )
                if not role.is_system_role:
                    role.is_system_role = True
                    role.save(update_fields=['is_system_role'])
                role_count += 1
                for code in codes:
                    perm = perm_by_code.get(code)
                    if not perm:
                        continue
                    _, created = RolePermission.objects.get_or_create(
                        role=role, permission=perm)
                    if created:
                        grant_count += 1
        self.stdout.write(self.style.SUCCESS(
            f'System roles: {role_count}, new permission grants: {grant_count}'))
        self.stdout.write(self.style.SUCCESS('seed_orgrbac complete.'))
