"""
Ensure announcements.view / announcements.manage permissions exist and are
granted to the hr (legacy), internal_hr, deployed_hr role slugs.

The seed_rbac command creates these idempotently, but Railway's first
deployment ran before announcements was added to MODULES, so the grants
are missing.  A data migration guarantees they land on every environment
that runs `migrate --noinput`.
"""
from django.db import migrations

_SLUGS = ['hr', 'internal_hr', 'deployed_hr', 'company_admin']


def grant_announcement_perms(apps, schema_editor):
    Permission = apps.get_model('core', 'Permission')
    Role = apps.get_model('core', 'Role')
    RolePermission = apps.get_model('core', 'RolePermission')

    for codename, module, description in [
        ('announcements.view', 'announcements', 'View announcements'),
        ('announcements.manage', 'announcements', 'Manage announcements'),
    ]:
        perm, _ = Permission.objects.get_or_create(
            codename=codename,
            defaults={'module': module, 'description': description},
        )
        for slug in _SLUGS:
            for role in Role.objects.filter(slug=slug):
                RolePermission.objects.get_or_create(role=role, permission=perm)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0005_staffassignment'),
    ]

    operations = [
        migrations.RunPython(grant_announcement_perms, noop),
    ]
