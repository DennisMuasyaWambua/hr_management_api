"""
Add matching module permissions and grant them to HR roles.
"""
from django.db import migrations

_MATCHING_PERMS = [
    ('matching.view', 'matching', 'View matching scores'),
    ('matching.manage', 'matching', 'Run matching engine'),
]

_HR_SLUGS = ('internal_hr', 'deployed_hr', 'hr', 'company_admin')


def add_matching_perms(apps, schema_editor):
    Role = apps.get_model('core', 'Role')
    Permission = apps.get_model('core', 'Permission')
    RolePermission = apps.get_model('core', 'RolePermission')

    perms = []
    for codename, module, description in _MATCHING_PERMS:
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
        ('core', '0011_crm_rbac'),
    ]

    operations = [
        migrations.RunPython(add_matching_perms, reverse_code=noop),
    ]
