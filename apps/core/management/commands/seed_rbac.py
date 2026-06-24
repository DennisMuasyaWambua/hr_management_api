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
           'compliance', 'background_checks',
           'announcements', 'recruitment', 'medical', 'performance', 'training',
           'onboarding', 'actions', 'workflows', 'talent_pools', 'referrals', 'crm',
           'matching', 'analytics', 'lms', 'performance']

# Strict role chain (lower rank = more authority):
#   super_admin > company_admin > internal_hr > deployed_hr
#   > internal_manager > deployed_manager > white_collar_employee > blue_collar_employee
# Legacy slugs (hr/manager/employee) are kept so existing assignments/sessions
# keep resolving while data is migrated to the granular roles.
SYSTEM_ROLES = [
    ('super_admin', 'Super Admin', 0),
    ('company_admin', 'Company Admin', 10),
    ('internal_hr', 'Internal HR', 20),
    ('deployed_hr', 'Deployed HR', 25),
    ('internal_manager', 'Internal Manager', 30),
    ('deployed_manager', 'Deployed Manager', 35),
    ('white_collar_employee', 'White Collar Employee', 40),
    ('blue_collar_employee', 'Blue Collar Employee', 45),
    # Legacy (back-compat)
    ('hr', 'HR (legacy)', 20),
    ('manager', 'Manager (legacy)', 30),
    ('employee', 'Employee (legacy)', 40),
]

# Default grants per role slug. Payroll is HR-and-above ONLY (hard rule).
# Internal vs deployed share the same capability set — deployed scoping (only
# assigned employees) is enforced at the queryset level, not via permissions.
_HR_GRANTS = ['payroll.view', 'payroll.manage', 'allowances.view', 'allowances.manage',
              'overtime.view', 'overtime.manage', 'reimbursements.view',
              'reimbursements.manage', 'disciplinary.view', 'disciplinary.manage',
              'exits.view', 'exits.manage', 'leave.view', 'leave.manage',
              'certificates.view', 'certificates.manage', 'attendance.view',
              'geofence.view', 'notifications.view', 'notifications.manage',
              'audit.view', 'share.manage', 'share.view', 'compliance.view',
              'statutory_rates.view', 'background_checks.view',
              'background_checks.manage',
              'announcements.view', 'announcements.manage',
              'recruitment.view', 'recruitment.manage',
              'medical.view', 'medical.manage',
              'performance.view', 'performance.manage',
              'training.view', 'training.manage',
              'onboarding.view', 'onboarding.manage',
              'actions.view', 'actions.manage',
              'workflows.view', 'workflows.manage',
              'talent_pools.view', 'talent_pools.manage',
              'referrals.view', 'referrals.manage',
              'crm.view', 'crm.manage',
              'matching.view', 'matching.manage',
              'analytics.view', 'analytics.manage',
              'lms.view', 'lms.manage',
              'performance.view', 'performance.manage']
_MANAGER_GRANTS = ['leave.view', 'leave.manage', 'overtime.view', 'overtime.manage',
                   'attendance.view', 'announcements.view', 'recruitment.view',
                   'lms.view', 'performance.view']
_EMPLOYEE_GRANTS = ['leave.view', 'overtime.view', 'reimbursements.view',
                    'attendance.view', 'lms.view', 'performance.view']

DEFAULT_GRANTS = {
    'super_admin': ['*'],
    'company_admin': ['*'],  # within their company; cross-company blocked by scoping
    'internal_hr': _HR_GRANTS,
    'deployed_hr': _HR_GRANTS,
    'internal_manager': _MANAGER_GRANTS,
    'deployed_manager': _MANAGER_GRANTS,
    'white_collar_employee': _EMPLOYEE_GRANTS,
    # Blue-collar additionally clock in/out (attendance.manage).
    'blue_collar_employee': _EMPLOYEE_GRANTS + ['attendance.manage'],
    # Legacy
    'hr': _HR_GRANTS,
    'manager': _MANAGER_GRANTS,
    'employee': _EMPLOYEE_GRANTS,
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
