"""
Add 20 more employees to the Sheer Logic demo company so the payroll page has a
fuller roster. Mirrors the shape used by seed_demo (Django auth user + AppUser
for name resolution + EmployeeProfile, back-linked) so the new rows show real
names and are payable.

Idempotent — fixed UUIDs, get_or_create. Run:
    python manage.py seed_more_employees
"""
import datetime
import random
import uuid

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

DjangoUser = get_user_model()

# Default target: the Sheer Logic Technologies demo company.
DEFAULT_COMPANY_ID = uuid.UUID('a1b2c3d4-0002-0002-0002-000000000002')
MANAGER_UID = uuid.UUID('a1b2c3d4-0003-0003-0003-000000000011')
# Stable namespace so re-runs are idempotent and per-company IDs never collide.
NS = uuid.UUID('5f1b9d2c-0000-0000-0000-0000000000ff')

# (suffix, full_name, title, dept, emp_type, worker_class, salary, method)
# suffixes 0030-0049 — distinct from seed_demo's 0010/0011/0020-0027.
ROSTER = [
    ('0030', 'Brian Otieno',     'Software Engineer',     'Engineering',      'full_time', 'white_collar', 110_000, 'mpesa'),
    ('0031', 'Cynthia Wanjiru',  'Accountant',            'Finance',          'full_time', 'white_collar',  85_000, 'bank'),
    ('0032', 'Dennis Kariuki',   'Logistics Officer',     'Operations',       'full_time', 'white_collar',  72_000, 'mpesa'),
    ('0033', 'Esther Akinyi',    'Sales Representative',  'Sales',            'full_time', 'white_collar',  65_000, 'mpesa'),
    ('0034', 'Felix Mwangi',     'QA Engineer',           'Engineering',      'full_time', 'white_collar',  90_000, 'bank'),
    ('0035', 'Gloria Chebet',    'Recruiter',             'Human Resources',  'full_time', 'white_collar',  68_000, 'mpesa'),
    ('0036', 'Henry Omondi',     'Machine Operator',      'Production',       'contract',  'blue_collar',   48_000, 'mpesa'),
    ('0037', 'Irene Nyambura',   'Marketing Officer',     'Marketing',        'full_time', 'white_collar',  70_000, 'bank'),
    ('0038', 'Joseph Maina',     'Security Guard',        'Security',         'full_time', 'blue_collar',   38_000, 'mpesa'),
    ('0039', 'Kevin Barasa',     'Support Technician',    'IT',               'full_time', 'white_collar',  60_000, 'mpesa'),
    ('0040', 'Lucy Wairimu',     'Payroll Clerk',         'Finance',          'full_time', 'white_collar',  62_000, 'bank'),
    ('0041', 'Martin Kiprop',    'Driver',                'Operations',       'contract',  'blue_collar',   42_000, 'mpesa'),
    ('0042', 'Nancy Atieno',     'Customer Service Agent','Customer Service', 'full_time', 'white_collar',  55_000, 'mpesa'),
    ('0043', 'Oscar Mutiso',     'DevOps Engineer',       'Engineering',      'full_time', 'white_collar', 130_000, 'bank'),
    ('0044', 'Patricia Wambui',  'Procurement Officer',   'Procurement',      'full_time', 'white_collar',  75_000, 'mpesa'),
    ('0045', 'Quincy Ochieng',   'Storekeeper',           'Warehouse',        'full_time', 'blue_collar',   45_000, 'mpesa'),
    ('0046', 'Rose Njoki',       'Admin Assistant',       'Administration',   'full_time', 'white_collar',  52_000, 'bank'),
    ('0047', 'Stephen Kamau',    'Account Manager',       'Sales',            'full_time', 'white_collar',  95_000, 'bank'),
    ('0048', 'Teresa Adhiambo',  'Quality Inspector',     'Production',       'full_time', 'blue_collar',   50_000, 'mpesa'),
    ('0049', 'Victor Mwenda',    'Data Analyst',          'Engineering',      'full_time', 'white_collar',  88_000, 'mpesa'),
]

BANKS = ['Equity Bank', 'KCB', 'Cooperative', 'Stanbic', 'Absa']


class Command(BaseCommand):
    help = 'Add 20 more demo employees to the Sheer Logic company.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--company', default=str(DEFAULT_COMPANY_ID),
            help='Target company by UUID or name substring.')

    def handle(self, *args, **opts):
        from apps.core.models import AppUser
        from apps.payroll.models import Company, EmployeeProfile

        target = opts['company']
        company = None
        try:
            company = Company.objects.filter(id=uuid.UUID(target)).first()
        except (ValueError, AttributeError):
            pass
        if not company:
            company = Company.objects.filter(name__icontains=target, is_deleted=False).first()
        if not company:
            self.stderr.write(f'Company not found: {target}')
            return

        company_id = company.id
        tenant_id = company.tenant_id
        # Per-company deterministic email suffix from the company name.
        slug = ''.join(c for c in company.name.lower() if c.isalnum())[:12] or 'co'
        is_default = company_id == DEFAULT_COMPANY_ID
        # Employee-number prefix: 'SL' for the demo co, else company initials.
        empno_prefix = 'SL' if is_default else (
            ''.join(w[0] for w in company.name.split()[:3]).upper() or 'EMP')
        self.stdout.write(f'Target: {company.name} ({company_id})')

        today = datetime.date.today()
        created_count = 0

        for (suffix, name, title, dept, etype, wclass, salary, method) in ROSTER:
            # Demo company keeps its original stable IDs; other companies get
            # deterministic uuid5 IDs namespaced by company so re-runs are
            # idempotent and never collide across companies.
            if is_default:
                uid = uuid.UUID(f'a1b2c3d4-0003-0003-0003-{suffix.zfill(12)}')
                emp_id = uuid.UUID(f'a1b2c3d4-0004-0004-0004-{suffix.zfill(12)}')
            else:
                uid = uuid.uuid5(NS, f'{company_id}-user-{suffix}')
                emp_id = uuid.uuid5(NS, f'{company_id}-emp-{suffix}')
            first, *rest = name.split()
            email = f'{first.lower()}.{("".join(rest) or "x").lower()}.{slug}@sheerlogic.co.ke'
            mpesa = f'+2547{random.randint(10000000, 99999999)}'

            # Django auth user
            dj_user, _ = DjangoUser.objects.get_or_create(
                username=email,
                defaults=dict(email=email, first_name=first, last_name=' '.join(rest)),
            )

            # AppUser (drives payroll name resolution)
            app_user, _ = AppUser.objects.get_or_create(
                id=uid,
                defaults=dict(
                    tenant_id=tenant_id, company_id=company_id,
                    full_name=name, email=email, role='employee',
                    is_active=True, phone=mpesa, auth_user=dj_user,
                ),
            )

            emp, created = EmployeeProfile.objects.get_or_create(
                id=emp_id,
                defaults=dict(
                    tenant_id=tenant_id, company=company, user_id=uid,
                    employee_number=f'{empno_prefix}-{suffix[-3:]}',
                    department=dept, job_title=title,
                    employment_type=etype, employment_status='active',
                    worker_class=wclass, manager_id=(MANAGER_UID if is_default else None),
                    start_date=today - datetime.timedelta(days=random.randint(2, 40) * 30),
                    salary=salary, payment_method=method,
                    bank_name=(random.choice(BANKS) if method == 'bank' else None),
                    bank_account=(f'0{random.randint(100000000, 999999999)}' if method == 'bank' else None),
                    mpesa_number=(mpesa if method == 'mpesa' else None),
                    nssf_number=f'NSSF{suffix}', nhif_number=f'SHA{suffix}',
                    kra_pin=f'A{random.randint(100000000, 999999999)}Z',
                    gender=random.choice(['male', 'female']),
                    date_of_birth=today - datetime.timedelta(days=random.randint(24, 50) * 365),
                    id_number=str(random.randint(20000000, 39999999)),
                    nationality='Kenyan',
                    next_of_kin_name='Next of Kin',
                    next_of_kin_phone=f'+2547{random.randint(10000000, 99999999)}',
                    next_of_kin_relationship='Spouse',
                ),
            )
            if app_user.employee_id != emp_id:
                app_user.employee_id = emp_id
                app_user.save(update_fields=['employee_id'])
            if created:
                created_count += 1

        total = EmployeeProfile.objects.filter(
            company_id=company_id, is_deleted=False).count()
        self.stdout.write(self.style.SUCCESS(
            f'Added {created_count} new employees (roster {len(ROSTER)}). '
            f'Company now has {total} active employees.'))
