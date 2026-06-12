"""
Seed system roles and module permissions.

Run: python manage.py seed_rbac
Idempotent — safe to re-run after adding modules.
"""
from django.core.management.base import BaseCommand

from apps.core.models import Permission, Role, RolePermission

MODULES = ['payroll', 'allowances', 'overtime', 'reimbursements',
           'statutory_rates', 'disciplinary', 'exits', 'leave', 'certificates',
           'attendance', 'geofence', 'notifications', 'rbac', 'audit', 'share',
           'compliance']

SYSTEM_ROLES = [
    ('super_admin', 'Super Admin', 0),
    ('company_admin', 'Company Admin', 10),
    ('hr', 'HR', 20),
    ('manager', 'Manager', 30),
    ('employee', 'Employee', 40),
]

# Default grants per role slug. Payroll is HR-and-above ONLY (hard rule).
DEFAULT_GRANTS = {
    'super_admin': ['*'],
    'company_admin': ['*'],  # within their company; cross-company blocked by scoping
    'hr': ['payroll.view', 'payroll.manage', 'allowances.view', 'allowances.manage',
           'overtime.view', 'overtime.manage', 'reimbursements.view',
           'reimbursements.manage', 'disciplinary.view', 'disciplinary.manage',
           'exits.view', 'exits.manage', 'leave.view', 'leave.manage',
           'certificates.view', 'certificates.manage', 'attendance.view',
           'geofence.view', 'notifications.view', 'notifications.manage',
           'audit.view', 'share.manage', 'share.view', 'compliance.view',
           'statutory_rates.view'],
    'manager': ['leave.view', 'leave.manage', 'overtime.view', 'overtime.manage',
                'attendance.view'],
    'employee': ['leave.view', 'overtime.view', 'reimbursements.view',
                 'attendance.view'],
}


class Command(BaseCommand):
    help = 'Seed system RBAC roles and permissions'

    def handle(self, *args, **options):
        perms = {}
        for module in MODULES:
            for act in ('view', 'manage'):
                codename = f'{module}.{act}'
                perm, _ = Permission.objects.get_or_create(
                    codename=codename,
                    defaults={'module': module,
                              'description': f'{act.title()} {module.replace("_", " ")}'})
                perms[codename] = perm

        for slug, name, rank in SYSTEM_ROLES:
            role, _ = Role.objects.get_or_create(
                company_id=None, slug=slug,
                defaults={'name': name, 'rank': rank, 'is_system': True})
            grants = DEFAULT_GRANTS[slug]
            wanted = perms.values() if grants == ['*'] else \
                [perms[c] for c in grants if c in perms]
            for perm in wanted:
                RolePermission.objects.get_or_create(role=role, permission=perm)

        self.stdout.write(self.style.SUCCESS(
            f'Seeded {len(perms)} permissions across {len(SYSTEM_ROLES)} system roles.'))
