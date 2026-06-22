"""
Data migration: grant the 5 remaining missing RBAC modules to hr roles.
(announcements was handled by 0006_fix_announcement_rbac.)

seed_rbac now includes all modules so fresh deploys are covered;
this migration covers existing Railway databases.
"""
from django.db import migrations

NEW_MODULES = [
    'recruitment', 'medical', 'performance', 'training', 'onboarding',
]

HR_ROLE_SLUGS = ('internal_hr', 'deployed_hr', 'hr')


def grant_modules(apps, schema_editor):
    Permission = apps.get_model('core', 'Permission')
    Role = apps.get_model('core', 'Role')
    RolePermission = apps.get_model('core', 'RolePermission')

    perms = []
    for module in NEW_MODULES:
        for action in ('view', 'manage'):
            perm, _ = Permission.objects.get_or_create(
                codename=f'{module}.{action}',
                defaults={
                    'module': module,
                    'description': f'{action.title()} {module.replace("_", " ")}',
                },
            )
            perms.append(perm)

    for slug in HR_ROLE_SLUGS:
        for role in Role.objects.filter(slug=slug):
            for perm in perms:
                RolePermission.objects.get_or_create(role=role, permission=perm)


def revoke_modules(apps, schema_editor):
    Permission = apps.get_model('core', 'Permission')
    RolePermission = apps.get_model('core', 'RolePermission')

    codenames = [
        f'{m}.{a}' for m in NEW_MODULES for a in ('view', 'manage')
    ]
    RolePermission.objects.filter(
        permission__codename__in=codenames
    ).delete()
    Permission.objects.filter(codename__in=codenames).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0006_fix_announcement_rbac'),
    ]

    operations = [
        migrations.RunPython(grant_modules, reverse_code=revoke_modules),
    ]
