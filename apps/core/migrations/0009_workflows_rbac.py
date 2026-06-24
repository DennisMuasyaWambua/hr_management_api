"""
Add workflows module permissions and grant them to HR roles.
"""
from django.db import migrations

_WORKFLOWS_PERMS = [
    ('workflows.view', 'workflows', 'View workflows'),
    ('workflows.manage', 'workflows', 'Manage workflows'),
]

_HR_SLUGS = ('internal_hr', 'deployed_hr', 'hr', 'company_admin')


def add_workflows_perms(apps, schema_editor):
    Role = apps.get_model('core', 'Role')
    Permission = apps.get_model('core', 'Permission')
    RolePermission = apps.get_model('core', 'RolePermission')

    perms = []
    for codename, module, description in _WORKFLOWS_PERMS:
        perm, _ = Permission.objects.get_or_create(
            codename=codename,
            defaults={'module': module, 'description': description},
        )
        perms.append(perm)

    for role in Role.objects.filter(slug__in=('super_admin', 'company_admin'), company_id=None):
        for perm in perms:
            RolePermission.objects.get_or_create(role=role, permission=perm)

    for slug in _HR_SLUGS:
        for role in Role.objects.filter(slug=slug, company_id=None):
            for perm in perms:
                RolePermission.objects.get_or_create(role=role, permission=perm)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0008_seed_system_roles_and_actions_rbac'),
    ]

    operations = [
        migrations.RunPython(add_workflows_perms, reverse_code=noop),
    ]
