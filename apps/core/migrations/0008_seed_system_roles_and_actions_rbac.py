"""
Ensure system roles exist and grant actions.view / actions.manage to HR roles.

Roles are normally created by `seed_rbac`, which does not run during tests.
This migration makes the test DB self-consistent so view-level RBAC tests pass.
"""
from django.db import migrations

_SYSTEM_ROLES = [
    ('super_admin', 'Super Admin', 0),
    ('company_admin', 'Company Admin', 10),
    ('internal_hr', 'Internal HR', 20),
    ('deployed_hr', 'Deployed HR', 25),
    ('internal_manager', 'Internal Manager', 30),
    ('deployed_manager', 'Deployed Manager', 35),
    ('white_collar_employee', 'White Collar Employee', 40),
    ('blue_collar_employee', 'Blue Collar Employee', 45),
    ('hr', 'HR (legacy)', 20),
    ('manager', 'Manager (legacy)', 30),
    ('employee', 'Employee (legacy)', 40),
]

_HR_SLUGS = ('internal_hr', 'deployed_hr', 'hr', 'company_admin')

_ACTIONS_PERMS = [
    ('actions.view', 'actions', 'View actions'),
    ('actions.manage', 'actions', 'Manage actions'),
]


def seed_roles_and_actions(apps, schema_editor):
    Role = apps.get_model('core', 'Role')
    Permission = apps.get_model('core', 'Permission')
    RolePermission = apps.get_model('core', 'RolePermission')

    for slug, name, rank in _SYSTEM_ROLES:
        Role.objects.get_or_create(
            company_id=None, slug=slug,
            defaults={'name': name, 'rank': rank, 'is_system': True},
        )

    perms = []
    for codename, module, description in _ACTIONS_PERMS:
        perm, _ = Permission.objects.get_or_create(
            codename=codename,
            defaults={'module': module, 'description': description},
        )
        perms.append(perm)

    wildcard_roles = Role.objects.filter(slug__in=('super_admin', 'company_admin'), company_id=None)
    all_perms = list(Permission.objects.all())
    for role in wildcard_roles:
        for perm in all_perms:
            RolePermission.objects.get_or_create(role=role, permission=perm)

    for slug in _HR_SLUGS:
        for role in Role.objects.filter(slug=slug, company_id=None):
            for perm in perms:
                RolePermission.objects.get_or_create(role=role, permission=perm)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0007_grant_missing_rbac_modules'),
    ]

    operations = [
        migrations.RunPython(seed_roles_and_actions, reverse_code=noop),
    ]
