from django.db import migrations

_PERMS = [
    ('lms.view', 'lms', 'View LMS'),
    ('lms.manage', 'lms', 'Manage LMS'),
]
_ADMIN_SLUGS = ('super_admin', 'company_admin')
_HR_SLUGS = ('internal_hr', 'deployed_hr', 'hr')
_MANAGER_SLUGS = ('internal_manager', 'deployed_manager', 'manager')
_EMPLOYEE_SLUGS = ('white_collar_employee', 'blue_collar_employee', 'employee')


def add_perms(apps, schema_editor):
    Role = apps.get_model('core', 'Role')
    Permission = apps.get_model('core', 'Permission')
    RolePermission = apps.get_model('core', 'RolePermission')

    perms = []
    for codename, module, description in _PERMS:
        perm, _ = Permission.objects.get_or_create(
            codename=codename,
            defaults={'module': module, 'description': description})
        perms.append(perm)

    view_perm = next(p for p in perms if p.codename == 'lms.view')
    manage_perm = next(p for p in perms if p.codename == 'lms.manage')

    for slug in _ADMIN_SLUGS + _HR_SLUGS:
        for role in Role.objects.filter(slug=slug, company_id=None):
            for perm in perms:
                RolePermission.objects.get_or_create(role=role, permission=perm)

    for slug in _MANAGER_SLUGS + _EMPLOYEE_SLUGS:
        for role in Role.objects.filter(slug=slug, company_id=None):
            RolePermission.objects.get_or_create(role=role, permission=view_perm)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [('core', '0013_analytics_rbac')]
    operations = [migrations.RunPython(add_perms, reverse_code=noop)]
