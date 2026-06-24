"""
Add talent_pools and referrals module permissions and grant them to HR roles.
"""
from django.db import migrations

_CRM_PERMS = [
    ('talent_pools.view', 'talent_pools', 'View talent pools'),
    ('talent_pools.manage', 'talent_pools', 'Manage talent pools'),
    ('referrals.view', 'referrals', 'View referrals'),
    ('referrals.manage', 'referrals', 'Manage referrals'),
    # recruitment was seeded in 0007 but before roles existed — fix here
    ('recruitment.view', 'recruitment', 'View recruitment'),
    ('recruitment.manage', 'recruitment', 'Manage recruitment'),
]

_HR_SLUGS = ('internal_hr', 'deployed_hr', 'hr', 'company_admin')


def add_crm_perms(apps, schema_editor):
    Role = apps.get_model('core', 'Role')
    Permission = apps.get_model('core', 'Permission')
    RolePermission = apps.get_model('core', 'RolePermission')

    perms = []
    for codename, module, description in _CRM_PERMS:
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
        ('core', '0009_workflows_rbac'),
    ]

    operations = [
        migrations.RunPython(add_crm_perms, reverse_code=noop),
    ]
