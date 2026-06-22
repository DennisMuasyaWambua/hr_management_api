"""
Comprehensive demo seed for Sheer Logic HR — covers every module visible
across the Dashboard, PWA and Careers frontends.

Run:
    python manage.py seed_demo

Idempotent — safe to re-run. Calls seed_rbac + seed_statutory internally.
"""
import datetime
import random
import uuid

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

DjangoUser = get_user_model()

# ── Fixed root IDs (stable across re-runs) ──────────────────────────────────
TENANT_ID  = uuid.UUID('a1b2c3d4-0001-0001-0001-000000000001')
COMPANY_ID = uuid.UUID('a1b2c3d4-0002-0002-0002-000000000002')

# ── Kenyan tax helpers ───────────────────────────────────────────────────────
def _paye(gross):
    bands = [(24_000, .10), (8_333, .25), (467_667, .30), (300_000, .325)]
    tax, rem = 0, float(gross)
    for cap, rate in bands:
        chunk = min(rem, cap)
        tax += chunk * rate
        rem  -= chunk
        if rem <= 0:
            break
    if rem > 0:
        tax += rem * .35
    return max(0.0, round(tax - 2_400, 2))          # personal relief = 2,400

def _nssf(gross):
    g = float(gross)
    return round(min(g, 7_000) * .06 + max(0, min(g, 36_000) - 7_000) * .06, 2)

def _shif(gross):
    return max(300.0, round(float(gross) * .0275, 2))

def _levy(gross):
    return round(float(gross) * .015, 2)

def _net(gross, allowances=0):
    g = float(gross) + float(allowances)
    return round(g - _paye(g) - _nssf(g) - _shif(g) - _levy(g), 2)


class Command(BaseCommand):
    help = 'Seed realistic demo data end-to-end (Dashboard + PWA + Careers)'

    def handle(self, *args, **opts):
        self.stdout.write('>  seed_rbac …')
        call_command('seed_rbac', verbosity=0)
        self.stdout.write('>  seed_statutory …')
        call_command('seed_statutory', verbosity=0)

        self._company()
        self._users()
        self._employees()
        self._allowances()
        self._attendance()
        self._leave()
        self._overtime()
        self._reimbursements()
        self._payroll()
        self._onboarding()
        self._disciplinary()
        self._exits()
        self._certificates()
        self._medical()
        self._background_checks()
        self._performance()
        self._training()
        self._announcements()
        self._recruitment()
        self._notification_templates()
        self._audit_log()

        self.stdout.write(self.style.SUCCESS('OK  Demo seed complete.'))

    # ────────────────────────────────────────────────────────────────────────
    # COMPANY
    # ────────────────────────────────────────────────────────────────────────
    def _company(self):
        from apps.payroll.models import Company
        company, created = Company.objects.get_or_create(
            id=COMPANY_ID,
            defaults=dict(
                tenant_id=TENANT_ID,
                name='Sheer Logic Technologies Ltd',
                industry='Technology & HR Services',
                country='Kenya',
                city='Nairobi',
                contact_email='hr@sheerlogic.co.ke',
                is_active=True,
                background_check_required=True,
                background_check_blocks_hiring=False,
                company_bank_name='Equity Bank',
                company_bank_account='0190263789001',
                company_bank_branch='Upperhill Branch',
                mpesa_paybill_number='522522',
            ),
        )
        self._company_obj = company
        self.stdout.write(f"  company: {'created' if created else 'exists'}")

    # ────────────────────────────────────────────────────────────────────────
    # USERS  (Django auth + AppUser)
    # ────────────────────────────────────────────────────────────────────────
    def _users(self):
        from apps.core.models import AppUser
        specs = [
            # (uuid-suffix, full_name, email, password, role)
            ('0010', 'Carol Njeri', 'carol.njeri@sheerlogic.co.ke',  'HRAdmin@2026!',  'hr_admin'),
            ('0011', 'James Mwangi','james.mwangi@sheerlogic.co.ke','Manager@2026!',  'manager'),
            ('0020', 'Grace Wanjiku','grace.wanjiku@sheerlogic.co.ke','Emp@2026!',    'employee'),
            ('0021', 'Amina Hassan','amina.hassan@sheerlogic.co.ke', 'Emp@2026!',     'employee'),
            ('0022', 'David Kipchoge','david.kipchoge@sheerlogic.co.ke','Emp@2026!', 'employee'),
            ('0023', 'Faith Achieng','faith.achieng@sheerlogic.co.ke','Emp@2026!',   'employee'),
            ('0024', 'Peter Otieno','peter.otieno@sheerlogic.co.ke','Emp@2026!',     'employee'),
            ('0025', 'Mary Njeri',  'mary.njeri@sheerlogic.co.ke',  'Emp@2026!',     'employee'),
            ('0026', 'Samuel Mutua','samuel.mutua@sheerlogic.co.ke','Emp@2026!',     'employee'),
            ('0027', 'Linda Kamau', 'linda.kamau@sheerlogic.co.ke', 'Emp@2026!',     'employee'),
        ]
        self._app_users = {}
        for suffix, name, email, pwd, role in specs:
            uid = uuid.UUID(f'a1b2c3d4-0003-0003-0003-{suffix.zfill(12)}')
            # Django auth user
            dj_user, _ = DjangoUser.objects.get_or_create(
                username=email,
                defaults=dict(email=email, first_name=name.split()[0],
                              last_name=' '.join(name.split()[1:]))
            )
            dj_user.set_password(pwd)
            dj_user.save(update_fields=['password'])
            # AppUser
            app_user, created = AppUser.objects.get_or_create(
                id=uid,
                defaults=dict(
                    tenant_id=TENANT_ID,
                    company_id=COMPANY_ID,
                    full_name=name,
                    email=email,
                    role=role,
                    is_active=True,
                    phone=f'+2547{random.randint(10000000,99999999)}',
                    auth_user=dj_user,
                )
            )
            if not created and app_user.auth_user != dj_user:
                app_user.auth_user = dj_user
                app_user.save(update_fields=['auth_user'])
            self._app_users[suffix] = app_user
        self.stdout.write(f"  users: {len(specs)} processed")

    # ────────────────────────────────────────────────────────────────────────
    # EMPLOYEE PROFILES
    # ────────────────────────────────────────────────────────────────────────
    def _employees(self):
        from apps.payroll.models import EmployeeProfile
        from apps.core.models import AppUser, UserRoleAssignment, Role

        today = datetime.date.today()
        manager_uid = uuid.UUID('a1b2c3d4-0003-0003-0003-000000000011')

        specs = [
            # (suffix, emp_no, title, dept, type, status, worker_class, salary, method, bank, mpesa, nssf, nhif, kra, gender, start_months_ago)
            ('0020','SL-001','Senior Software Engineer','Engineering','full_time','active','white_collar',120_000,'bank','Equity','0701234501','NSSF001','NHIF001','A001234567B','male',18),
            ('0021','SL-002','HR Specialist','Human Resources','full_time','active','white_collar', 75_000,'bank','KCB',   '0712345602','NSSF002','NHIF002','A002345678C','female',24),
            ('0022','SL-003','Operations Lead','Operations','full_time','active','white_collar', 85_000,'mpesa',None,'0723456703','NSSF003','NHIF003','A003456789D','male',12),
            ('0023','SL-004','Finance Analyst','Finance','full_time','active','white_collar', 80_000,'bank','Cooperative','0734567804','NSSF004','NHIF004','A004567890E','female',30),
            ('0024','SL-005','Warehouse Supervisor','Operations','full_time','active','blue_collar', 55_000,'mpesa',None,'0745678905','NSSF005','NHIF005','A005678901F','male',36),
            ('0025','SL-006','Production Technician','Production','contract','active','blue_collar', 45_000,'mpesa',None,'0756789006','NSSF006','NHIF006','A006789012G','female',8),
            ('0026','SL-007','Security Officer','Security','full_time','active','blue_collar', 40_000,'mpesa',None,'0767890107','NSSF007','NHIF007','A007890123H','male',48),
            ('0027','SL-008','Sales & Marketing Executive','Sales','full_time','active','white_collar', 70_000,'bank','Stanbic','0778901208','NSSF008','NHIF008','A008901234I','female',6),
        ]
        self._employees = {}
        for (suffix, emp_no, title, dept, etype, estatus, wclass, salary,
             method, bank, mpesa, nssf, nhif, kra, gender, months_ago) in specs:
            uid      = uuid.UUID(f'a1b2c3d4-0003-0003-0003-{suffix.zfill(12)}')
            emp_id   = uuid.UUID(f'a1b2c3d4-0004-0004-0004-{suffix.zfill(12)}')
            start    = today - datetime.timedelta(days=months_ago * 30)
            app_user = self._app_users[suffix]

            emp, created = EmployeeProfile.objects.get_or_create(
                id=emp_id,
                defaults=dict(
                    tenant_id=TENANT_ID,
                    company=self._company_obj,
                    user_id=uid,
                    employee_number=emp_no,
                    department=dept,
                    job_title=title,
                    employment_type=etype,
                    employment_status=estatus,
                    worker_class=wclass,
                    manager_id=manager_uid,
                    start_date=start,
                    salary=salary,
                    payment_method=method,
                    bank_name=bank,
                    bank_account=f'0{random.randint(100000000,999999999)}' if bank else None,
                    mpesa_number=mpesa,
                    nssf_number=nssf,
                    nhif_number=nhif,
                    kra_pin=kra,
                    gender=gender,
                    date_of_birth=today - datetime.timedelta(days=random.randint(25,45)*365),
                    id_number=str(random.randint(20000000,39999999)),
                    nationality='Kenyan',
                    next_of_kin_name='Next of Kin',
                    next_of_kin_phone=f'+2547{random.randint(10000000,99999999)}',
                    next_of_kin_relationship='Spouse',
                )
            )
            self._employees[suffix] = emp

            # Back-link AppUser → EmployeeProfile
            if app_user.employee_id != emp_id:
                app_user.employee_id = emp_id
                app_user.save(update_fields=['employee_id'])

        # Wire manager's employee profile
        mgr_emp_id = uuid.UUID('a1b2c3d4-0004-0004-0004-000000000011')
        mgr_app    = self._app_users['0011']
        mgr_emp, _ = EmployeeProfile.objects.get_or_create(
            id=mgr_emp_id,
            defaults=dict(
                tenant_id=TENANT_ID,
                company=self._company_obj,
                user_id=uuid.UUID('a1b2c3d4-0003-0003-0003-000000000011'),
                employee_number='SL-000',
                department='Management',
                job_title='Operations Manager',
                employment_type='full_time',
                employment_status='active',
                worker_class='white_collar',
                start_date=today - datetime.timedelta(days=60*30),
                salary=150_000,
                payment_method='bank',
                bank_name='Equity Bank',
                bank_account='0190000000001',
                nssf_number='NSSF000',
                nhif_number='NHIF000',
                kra_pin='A000000000Z',
                gender='male',
                nationality='Kenyan',
            )
        )
        self._manager_emp = mgr_emp
        if mgr_app.employee_id != mgr_emp_id:
            mgr_app.employee_id = mgr_emp_id
            mgr_app.save(update_fields=['employee_id'])
        self._all_employees = list(self._employees.values()) + [mgr_emp]
        self.stdout.write(f"  employees: {len(self._all_employees)} processed")

        # UserRoleAssignment for each AppUser
        from apps.core.models import Role, UserRoleAssignment
        role_map = {'hr_admin': 'internal_hr', 'manager': 'internal_manager', 'employee': 'white_collar_employee'}
        blue_collar_suffixes = {'0024','0025','0026'}
        for suffix, app_user in self._app_users.items():
            if suffix in blue_collar_suffixes:
                r_slug = 'blue_collar_employee'
            else:
                r_slug = role_map.get(app_user.role, 'white_collar_employee')
            role_obj = Role.objects.filter(slug=r_slug, company_id__isnull=True).first()
            if role_obj:
                UserRoleAssignment.objects.get_or_create(
                    user_id=app_user.id,
                    company_id=COMPANY_ID,
                    role=role_obj,
                    defaults=dict(tenant_id=TENANT_ID),
                )

    # ────────────────────────────────────────────────────────────────────────
    # ALLOWANCES & DEDUCTIONS
    # ────────────────────────────────────────────────────────────────────────
    def _allowances(self):
        from apps.hr.models import AllowanceType, EmployeeAllowance, DeductionType, EmployeeDeduction
        today = datetime.date.today()
        effective = today.replace(day=1)

        allow_specs = [
            ('Housing Allowance', True, False, 15_000),
            ('Transport Allowance', True, False, 5_000),
            ('Airtime Allowance', False, False, 1_500),
            ('Per Diem (Variable)', True, True, 0),
        ]
        self._allow_types = {}
        for name, taxable, variable, default_amt in allow_specs:
            at, _ = AllowanceType.objects.get_or_create(
                company_id=COMPANY_ID, name=name,
                defaults=dict(tenant_id=TENANT_ID, taxable=taxable,
                              is_variable=variable, default_amount=default_amt, is_active=True)
            )
            self._allow_types[name] = at

        deduct_specs = ['SACCO Loan', 'Salary Advance Recovery']
        self._deduct_types = {}
        for name in deduct_specs:
            dt, _ = DeductionType.objects.get_or_create(
                company_id=COMPANY_ID, name=name,
                defaults=dict(tenant_id=TENANT_ID, is_active=True)
            )
            self._deduct_types[name] = dt

        white_collar_suffixes = ['0020','0021','0022','0023','0027','0011']
        for suffix in white_collar_suffixes:
            emp = self._employees.get(suffix) or (self._manager_emp if suffix == '0011' else None)
            if not emp:
                continue
            EmployeeAllowance.objects.get_or_create(
                company_id=COMPANY_ID, employee_id=emp.id,
                allowance_type=self._allow_types['Housing Allowance'],
                defaults=dict(tenant_id=TENANT_ID, amount=15_000, effective_from=effective, is_active=True)
            )
            EmployeeAllowance.objects.get_or_create(
                company_id=COMPANY_ID, employee_id=emp.id,
                allowance_type=self._allow_types['Transport Allowance'],
                defaults=dict(tenant_id=TENANT_ID, amount=5_000, effective_from=effective, is_active=True)
            )

        # SACCO deduction for 3 employees
        for suffix in ['0020','0022','0024']:
            emp = self._employees.get(suffix)
            if emp:
                EmployeeDeduction.objects.get_or_create(
                    company_id=COMPANY_ID, employee_id=emp.id,
                    deduction_type=self._deduct_types['SACCO Loan'],
                    defaults=dict(tenant_id=TENANT_ID, amount=5_000, effective_from=effective, is_active=True)
                )
        self.stdout.write('  allowances & deductions: done')

    # ────────────────────────────────────────────────────────────────────────
    # ATTENDANCE (geofence + events)
    # ────────────────────────────────────────────────────────────────────────
    def _attendance(self):
        from apps.attendance.models import WorkZone, EmployeeZoneAssignment, AttendanceEvent, GeofenceViolation
        zone_id = uuid.UUID('a1b2c3d4-0005-0005-0005-000000000001')
        zone, _ = WorkZone.objects.get_or_create(
            id=zone_id,
            defaults=dict(
                tenant_id=TENANT_ID, company_id=COMPANY_ID,
                name='Sheer Logic HQ – Upperhill',
                center_lat=-1.2921, center_lng=36.8219,
                radius_m=300, work_start=datetime.time(8, 0),
                work_end=datetime.time(17, 0), is_active=True,
            )
        )

        blue_collar = [self._employees[s] for s in ('0024','0025','0026') if s in self._employees]
        for emp in blue_collar:
            EmployeeZoneAssignment.objects.get_or_create(
                employee_id=emp.id, zone=zone,
                defaults=dict(company_id=COMPANY_ID, is_active=True)
            )

        # 14 working days of check-in / check-out
        today = datetime.date.today()
        for emp in blue_collar:
            days_done = 0
            offset = 1
            while days_done < 14:
                day = today - datetime.timedelta(days=offset)
                offset += 1
                if day.weekday() >= 5:
                    continue
                days_done += 1
                ci_time = timezone.make_aware(datetime.datetime.combine(day, datetime.time(7, random.randint(45,59))))
                co_time = ci_time + datetime.timedelta(hours=8, minutes=random.randint(0,45))
                AttendanceEvent.objects.get_or_create(
                    company_id=COMPANY_ID, employee_id=emp.id,
                    event_type='check_in', time=ci_time,
                    defaults=dict(tenant_id=TENANT_ID, zone_id=zone_id,
                                  lat=-1.2921+random.uniform(-0.001,0.001),
                                  lng=36.8219+random.uniform(-0.001,0.001),
                                  in_zone=True, face_verified=True, source_app='pwa')
                )
                AttendanceEvent.objects.get_or_create(
                    company_id=COMPANY_ID, employee_id=emp.id,
                    event_type='check_out', time=co_time,
                    defaults=dict(tenant_id=TENANT_ID, zone_id=zone_id,
                                  lat=-1.2921+random.uniform(-0.002,0.002),
                                  lng=36.8219+random.uniform(-0.002,0.002),
                                  in_zone=True, face_verified=True, source_app='pwa')
                )

        # 1 geofence violation
        if blue_collar:
            emp = blue_collar[0]
            viol_start = timezone.now() - datetime.timedelta(days=3, hours=2)
            GeofenceViolation.objects.get_or_create(
                company_id=COMPANY_ID, employee_id=emp.id,
                started_at=viol_start,
                defaults=dict(
                    tenant_id=TENANT_ID, zone=zone,
                    ended_at=viol_start + datetime.timedelta(minutes=35),
                    distance_m=420.0, status='reason_submitted',
                    reason='Had to collect delivery at the gate'
                )
            )
        self.stdout.write('  attendance: done')

    # ────────────────────────────────────────────────────────────────────────
    # LEAVE
    # ────────────────────────────────────────────────────────────────────────
    def _leave(self):
        from apps.hr.models import LeaveRequest, LeaveBalance, LEAVE_TYPES
        from apps.core.models import AppUser
        today = datetime.date.today()
        yr = today.year
        hr_uid = uuid.UUID('a1b2c3d4-0003-0003-0003-000000000010')

        leave_entitlements = {
            'annual': 21, 'sick': 14, 'maternity': 90, 'paternity': 14,
            'study': 10, 'compassionate': 5, 'unpaid': 0,
            'adoption': 45, 'family': 3,
        }
        for emp in self._all_employees:
            for lt, total in leave_entitlements.items():
                if total == 0:
                    continue
                used = random.randint(0, max(0, total // 3))
                LeaveBalance.objects.get_or_create(
                    employee_id=emp.id, leave_type=lt, year=yr,
                    defaults=dict(
                        tenant_id=TENANT_ID, company_id=COMPANY_ID,
                        total_days=total, used_days=used,
                        remaining_days=total - used,
                    )
                )

        # Mix of leave requests
        leave_requests = [
            # (emp_suffix, lt, start_offset_days, duration, status)
            ('0020', 'annual',  -30, 5,  'approved'),
            ('0021', 'sick',    -14, 3,  'approved'),
            ('0022', 'annual',   5,  7,  'pending'),
            ('0023', 'annual',  20, 10,  'pending'),
            ('0024', 'sick',    -7,  2,  'approved'),
            ('0025', 'annual', -60,  5,  'approved'),
            ('0026', 'annual',  15,  3,  'pending'),
            ('0027', 'sick',    -3,  1,  'rejected'),
        ]
        for suffix, lt, offset, days, status in leave_requests:
            emp = self._employees.get(suffix)
            if not emp:
                continue
            start = today + datetime.timedelta(days=offset)
            end   = start + datetime.timedelta(days=days - 1)
            lr, created = LeaveRequest.objects.get_or_create(
                employee_id=emp.id, leave_type=lt, start_date=start,
                defaults=dict(
                    tenant_id=TENANT_ID, company_id=COMPANY_ID,
                    end_date=end, days_requested=days,
                    reason=f'{lt.title()} leave request',
                    status=status,
                    approved_by=hr_uid if status in ('approved','rejected') else None,
                    approved_at=timezone.now() - datetime.timedelta(days=abs(offset)//2) if status != 'pending' else None,
                    rejection_reason='Insufficient balance' if status == 'rejected' else None,
                )
            )
        self.stdout.write('  leave: done')

    # ────────────────────────────────────────────────────────────────────────
    # OVERTIME
    # ────────────────────────────────────────────────────────────────────────
    def _overtime(self):
        from apps.hr.models import OvertimeRequest
        today = datetime.date.today()
        mgr_uid = uuid.UUID('a1b2c3d4-0003-0003-0003-000000000011')
        specs = [
            ('0020', -10, 4.0, 'approved'),
            ('0022', -5,  3.5, 'pending'),
            ('0024', -3,  6.0, 'approved'),
        ]
        for suffix, offset, hours, status in specs:
            emp = self._employees.get(suffix)
            if not emp:
                continue
            OvertimeRequest.objects.get_or_create(
                company_id=COMPANY_ID, employee_id=emp.id,
                date=today - datetime.timedelta(days=abs(offset)),
                defaults=dict(
                    tenant_id=TENANT_ID, hours=hours,
                    rate_multiplier=1.5, reason='Project deadline',
                    status=status, manager_id=mgr_uid,
                    decided_by=mgr_uid if status == 'approved' else None,
                    decided_at=timezone.now() - datetime.timedelta(days=1) if status == 'approved' else None,
                )
            )
        self.stdout.write('  overtime: done')

    # ────────────────────────────────────────────────────────────────────────
    # REIMBURSEMENTS
    # ────────────────────────────────────────────────────────────────────────
    def _reimbursements(self):
        from apps.hr.models import Reimbursement
        specs = [
            ('0020', 'Transport', 2_400, 'approved', 'Client meeting transport'),
            ('0022', 'Per Diem',  6_000, 'paid',     'Mombasa site visit'),
            ('0023', 'Transport', 1_800, 'submitted', 'Training venue travel'),
        ]
        for suffix, cat, amt, status, desc in specs:
            emp = self._employees.get(suffix)
            if not emp:
                continue
            Reimbursement.objects.get_or_create(
                company_id=COMPANY_ID, employee_id=emp.id, category=cat,
                defaults=dict(
                    tenant_id=TENANT_ID, amount=amt, description=desc,
                    status=status,
                )
            )
        self.stdout.write('  reimbursements: done')

    # ────────────────────────────────────────────────────────────────────────
    # PAYROLL  (May 2026 = paid, June 2026 = pending_approval)
    # ────────────────────────────────────────────────────────────────────────
    def _payroll(self):
        from apps.payroll.models import PayrollRun, PayrollRecord, PaymentBatch
        from apps.payroll.approval_models import ApproverConfig, PayrollApprover, PayrollApproval

        hr_uid  = uuid.UUID('a1b2c3d4-0003-0003-0003-000000000010')
        mgr_uid = uuid.UUID('a1b2c3d4-0003-0003-0003-000000000011')

        run_specs = [
            (uuid.UUID('a1b2c3d4-0006-0006-0006-000000000001'), 5, 2026, 'paid'),
            (uuid.UUID('a1b2c3d4-0006-0006-0006-000000000002'), 6, 2026, 'pending_approval'),
        ]

        cfg, _ = ApproverConfig.objects.get_or_create(
            company_id=COMPANY_ID,
            defaults=dict(tenant_id=TENANT_ID, required_approvals=2, is_active=True)
        )
        PayrollApprover.objects.get_or_create(
            config=cfg, user_id=hr_uid,
            defaults=dict(name='Carol Njeri', email='carol.njeri@sheerlogic.co.ke', order=1)
        )
        PayrollApprover.objects.get_or_create(
            config=cfg, user_id=mgr_uid,
            defaults=dict(name='James Mwangi', email='james.mwangi@sheerlogic.co.ke', order=2)
        )

        for run_id, month, year, status in run_specs:
            total_gross = total_ded = total_net = 0
            run, run_created = PayrollRun.objects.get_or_create(
                id=run_id,
                defaults=dict(
                    tenant_id=TENANT_ID, company=self._company_obj,
                    period_month=month, period_year=year,
                    status=status, run_by=hr_uid,
                    completed_at=timezone.now() - datetime.timedelta(days=10) if status == 'paid' else None,
                )
            )

            for emp in self._all_employees:
                gross = float(emp.salary)
                allowances = 20_000 if emp.worker_class == 'white_collar' else 0
                g = gross + allowances
                paye  = _paye(g)
                nssf  = _nssf(g)
                shif  = _shif(g)
                levy  = _levy(g)
                sacco = 5_000 if emp.employee_number in ('SL-001','SL-003','SL-005') else 0
                other_ded = levy + sacco
                net   = round(g - paye - nssf - shif - other_ded, 2)
                total_gross += g
                total_ded   += paye + nssf + shif + other_ded
                total_net   += net

                rec_id = uuid.uuid5(run_id, str(emp.id))
                PayrollRecord.objects.get_or_create(
                    id=rec_id,
                    defaults=dict(
                        tenant_id=TENANT_ID,
                        payroll_run=run,
                        employee=emp,
                        gross_salary=round(g, 2),
                        paye=paye, nssf=nssf, nhif=shif,
                        helb=0, other_deductions=other_ded,
                        net_salary=net,
                        payment_method=emp.payment_method,
                        payment_status='paid' if status == 'paid' else 'pending',
                        paid_at=timezone.now() - datetime.timedelta(days=5) if status == 'paid' else None,
                    )
                )

            if run_created or run.total_gross == 0:
                run.total_gross = round(total_gross, 2)
                run.total_deductions = round(total_ded, 2)
                run.total_net = round(total_net, 2)
                run.save(update_fields=['total_gross','total_deductions','total_net'])

            # Payment batch for completed run
            if status == 'paid':
                PaymentBatch.objects.get_or_create(
                    payroll_run=run, payment_method='bank',
                    defaults=dict(
                        tenant_id=TENANT_ID, status='completed',
                        total_amount=round(total_net * 0.7, 2),
                        successful_amount=round(total_net * 0.7, 2),
                        record_count=7, successful_count=7,
                        completed_at=timezone.now() - datetime.timedelta(days=5),
                    )
                )
                PaymentBatch.objects.get_or_create(
                    payroll_run=run, payment_method='mpesa',
                    defaults=dict(
                        tenant_id=TENANT_ID, status='completed',
                        total_amount=round(total_net * 0.3, 2),
                        successful_amount=round(total_net * 0.3, 2),
                        record_count=3, successful_count=3,
                        completed_at=timezone.now() - datetime.timedelta(days=5),
                    )
                )
                # Approval records for paid run
                PayrollApproval.objects.get_or_create(
                    payroll_run_id=run_id, approver_user_id=hr_uid,
                    defaults=dict(
                        tenant_id=TENANT_ID, company_id=COMPANY_ID,
                        decision='approved', via='dashboard',
                        comment='Figures verified. Approved.',
                        signed_at=timezone.now() - datetime.timedelta(days=12),
                    )
                )
                PayrollApproval.objects.get_or_create(
                    payroll_run_id=run_id, approver_user_id=mgr_uid,
                    defaults=dict(
                        tenant_id=TENANT_ID, company_id=COMPANY_ID,
                        decision='approved', via='one_tap',
                        comment='Approved via one-tap link.',
                        signed_at=timezone.now() - datetime.timedelta(days=11),
                    )
                )
        self.stdout.write('  payroll: done')

    # ────────────────────────────────────────────────────────────────────────
    # ONBOARDING DOCUMENTS
    # ────────────────────────────────────────────────────────────────────────
    def _onboarding(self):
        from apps.hr.models import EmployeeOnboardingDocument
        doc_statuses = ['contract','id','nssf','nhif','kra_pin','bank_details']
        status_cycle = ['verified','verified','verified','uploaded','uploaded','missing']
        for emp in self._all_employees:
            for i, doc in enumerate(doc_statuses):
                st = status_cycle[i % len(status_cycle)]
                EmployeeOnboardingDocument.objects.get_or_create(
                    employee_id=emp.id, doc_type=doc,
                    defaults=dict(
                        status=st,
                        verified_at=timezone.now() - datetime.timedelta(days=30) if st == 'verified' else None,
                    )
                )
        self.stdout.write('  onboarding documents: done')

    # ────────────────────────────────────────────────────────────────────────
    # DISCIPLINARY
    # ────────────────────────────────────────────────────────────────────────
    def _disciplinary(self):
        from apps.hr.models import DisciplinaryRecord
        today = datetime.date.today()
        hr_uid = uuid.UUID('a1b2c3d4-0003-0003-0003-000000000010')
        emp = self._employees.get('0026')
        if emp:
            DisciplinaryRecord.objects.get_or_create(
                company_id=COMPANY_ID, employee_id=emp.id,
                kind='verbal_warning', title='Punctuality Warning',
                defaults=dict(
                    tenant_id=TENANT_ID,
                    status='resolved',
                    description='Employee arrived late on 5 consecutive days.',
                    issued_by=hr_uid,
                    starts_on=today - datetime.timedelta(days=60),
                    ends_on=today - datetime.timedelta(days=30),
                    outcome='Employee acknowledged and improved punctuality.',
                )
            )
        self.stdout.write('  disciplinary: done')

    # ────────────────────────────────────────────────────────────────────────
    # EMPLOYEE EXIT  (one in clearance stage)
    # ────────────────────────────────────────────────────────────────────────
    def _exits(self):
        from apps.hr.models import EmployeeExit, ExitClearanceItem
        today = datetime.date.today()
        hr_uid = uuid.UUID('a1b2c3d4-0003-0003-0003-000000000010')
        emp = self._employees.get('0025')
        if emp:
            exit_obj, _ = EmployeeExit.objects.get_or_create(
                company_id=COMPANY_ID, employee_id=emp.id,
                defaults=dict(
                    tenant_id=TENANT_ID, kind='resignation',
                    status='clearance',
                    reason='Pursuing further education',
                    notice_date=today - datetime.timedelta(days=14),
                    last_working_day=today + datetime.timedelta(days=16),
                    initiated_by=hr_uid,
                    final_dues={'notice_pay': 45_000, 'accrued_leave': 12_250},
                    final_dues_total=57_250,
                )
            )
            for item in ['Laptop Return', 'Gate Pass Cancellation', 'Finance Clearance',
                         'IT Equipment Return', 'HR File Completion']:
                ExitClearanceItem.objects.get_or_create(
                    exit=exit_obj, item=item,
                    defaults=dict(is_cleared=random.choice([True, False]))
                )
        self.stdout.write('  exits: done')

    # ────────────────────────────────────────────────────────────────────────
    # CERTIFICATES
    # ────────────────────────────────────────────────────────────────────────
    def _certificates(self):
        from apps.hr.models import EmployeeCertificate
        today = datetime.date.today()
        specs = [
            ('0024', 'Food Handler Certificate', 'Nairobi City County', today + datetime.timedelta(days=180)),
            ('0025', 'Food Handler Certificate', 'Nairobi City County', today - datetime.timedelta(days=30)),
            ('0026', 'Police Clearance Certificate', 'Kenya Police Service', today + datetime.timedelta(days=90)),
            ('0020', 'AWS Solutions Architect', 'Amazon Web Services',  today + datetime.timedelta(days=365)),
            ('0021', 'CHRP Certification', 'IHRM Kenya', today + datetime.timedelta(days=270)),
        ]
        for suffix, name, issuer, expiry in specs:
            emp = self._employees.get(suffix)
            if emp:
                EmployeeCertificate.objects.get_or_create(
                    company_id=COMPANY_ID, employee_id=emp.id, name=name,
                    defaults=dict(
                        tenant_id=TENANT_ID, issuer=issuer,
                        expiry_date=expiry,
                        alert_days_before=30, is_active=True,
                    )
                )
        self.stdout.write('  certificates: done')

    # ────────────────────────────────────────────────────────────────────────
    # MEDICAL RECORDS
    # ────────────────────────────────────────────────────────────────────────
    def _medical(self):
        from apps.hr.models import MedicalRecord
        today = datetime.date.today()
        for suffix, rtype, fitness in [('0024','Annual Medical','fit'),('0026','Occupational Health','fit'),('0025','Annual Medical','fit_with_conditions')]:
            emp = self._employees.get(suffix)
            if emp:
                MedicalRecord.objects.get_or_create(
                    company_id=COMPANY_ID, employee_id=emp.id, record_type=rtype,
                    defaults=dict(
                        tenant_id=TENANT_ID, fitness_status=fitness,
                        issued_by='Nairobi Hospital Occupational Health',
                        issued_date=today - datetime.timedelta(days=90),
                        expiry_date=today + datetime.timedelta(days=275),
                    )
                )
        self.stdout.write('  medical records: done')

    # ────────────────────────────────────────────────────────────────────────
    # BACKGROUND CHECKS
    # ────────────────────────────────────────────────────────────────────────
    def _background_checks(self):
        from apps.hr.models import BackgroundCheck
        hr_uid = uuid.UUID('a1b2c3d4-0003-0003-0003-000000000010')
        today = datetime.date.today()
        for suffix, ctype, status, verdict in [
            ('0026','criminal','passed','clean'),
            ('0024','criminal','passed','clean'),
            ('0020','employment','completed','clean'),
        ]:
            emp = self._employees.get(suffix)
            if emp:
                BackgroundCheck.objects.get_or_create(
                    company_id=COMPANY_ID, employee_id=emp.id, check_type=ctype,
                    defaults=dict(
                        tenant_id=TENANT_ID, status=status,
                        requested_by=hr_uid,
                        provider_name='Pinkerton Kenya',
                        completed_at=timezone.now() - datetime.timedelta(days=30),
                        result_summary='No adverse findings.',
                        clearance_date=today - datetime.timedelta(days=30),
                        expiry_date=today + datetime.timedelta(days=335),
                        verdict=verdict,
                    )
                )
        self.stdout.write('  background checks: done')

    # ────────────────────────────────────────────────────────────────────────
    # PERFORMANCE & TRAINING
    # ────────────────────────────────────────────────────────────────────────
    def _performance(self):
        from apps.hr.models import KpiAssignment, PerformanceReview
        today = datetime.date.today()
        mgr_uid = uuid.UUID('a1b2c3d4-0003-0003-0003-000000000011')
        hr_uid  = uuid.UUID('a1b2c3d4-0003-0003-0003-000000000010')
        q = ((today.month - 1) // 3) + 1
        yr = today.year

        kpi_targets = [
            {'name': 'Code quality', 'target': 90, 'weight': 30},
            {'name': 'Sprint delivery', 'target': 95, 'weight': 40},
            {'name': 'Code reviews', 'target': 20, 'weight': 30},
        ]
        for emp in self._all_employees:
            score = round(random.uniform(70, 98), 1)
            KpiAssignment.objects.get_or_create(
                company_id=COMPANY_ID, employee_id=emp.id,
                period_quarter=q, period_year=yr,
                defaults=dict(
                    tenant_id=TENANT_ID, targets=kpi_targets,
                    final_score=score, reviewed_by=mgr_uid,
                    submitted_at=timezone.now() - datetime.timedelta(days=15),
                )
            )

        review_specs = [('0020',4,'Q1 2026',True),('0022',3,'Q1 2026',False),('0021',5,'Q1 2026',True)]
        for suffix, rating, period, promo in review_specs:
            emp = self._employees.get(suffix)
            if emp:
                PerformanceReview.objects.get_or_create(
                    company_id=COMPANY_ID, employee_id=emp.id, period=period,
                    defaults=dict(
                        tenant_id=TENANT_ID, reviewer_id=mgr_uid, rating=rating,
                        strengths='Strong technical skills and team collaboration.',
                        improvements='Could improve documentation practices.',
                        promotion_recommended=promo,
                    )
                )
        self.stdout.write('  performance & KPIs: done')

    def _training(self):
        from apps.hr.models import TrainingSession, TrainingEnrollment
        today = datetime.date.today()
        sessions = [
            (uuid.UUID('a1b2c3d4-0007-0007-0007-000000000001'),
             'Data Protection & GDPR Awareness', 'IT Compliance Team',
             today - datetime.timedelta(days=45), today - datetime.timedelta(days=44), True, None),
            (uuid.UUID('a1b2c3d4-0007-0007-0007-000000000002'),
             'Fire Safety & Emergency Response', 'Kenya Red Cross',
             today + datetime.timedelta(days=10), today + datetime.timedelta(days=10), True, 'Operations'),
            (uuid.UUID('a1b2c3d4-0007-0007-0007-000000000003'),
             'Leadership Excellence Programme', 'Strathmore Business School',
             today - datetime.timedelta(days=20), today - datetime.timedelta(days=18), False, 'Management'),
        ]
        sess_objs = {}
        for sid, title, trainer, start, end, mandatory, dept in sessions:
            s, _ = TrainingSession.objects.get_or_create(
                id=sid,
                defaults=dict(
                    tenant_id=TENANT_ID, company_id=COMPANY_ID,
                    title=title, trainer_name=trainer,
                    start_date=start, end_date=end,
                    is_mandatory=mandatory, department=dept,
                )
            )
            sess_objs[sid] = s

        enroll_specs = [
            # (session_idx, emp_suffix, attendance_status, score)
            (0, '0020', 'completed', 88.0),
            (0, '0021', 'completed', 92.0),
            (0, '0022', 'completed', 78.0),
            (0, '0024', 'attended',  None),
            (1, '0024', 'enrolled',  None),
            (1, '0025', 'enrolled',  None),
            (1, '0026', 'enrolled',  None),
            (2, '0011', 'completed', 95.0),
            (2, '0022', 'completed', 85.0),
        ]
        sess_list = [sess_objs[s[0]] for s in sessions]
        for idx, suffix, att_status, score in enroll_specs:
            emp = self._employees.get(suffix) or (self._manager_emp if suffix == '0011' else None)
            if emp:
                TrainingEnrollment.objects.get_or_create(
                    session=sess_list[idx], employee_id=emp.id,
                    defaults=dict(attendance_status=att_status, score=score)
                )
        self.stdout.write('  training: done')

    # ────────────────────────────────────────────────────────────────────────
    # ANNOUNCEMENTS
    # ────────────────────────────────────────────────────────────────────────
    def _announcements(self):
        from apps.hr.models import Announcement
        hr_uid = uuid.UUID('a1b2c3d4-0003-0003-0003-000000000010')
        anns = [
            ('Q2 2026 Payroll Dates', 'June payroll will be processed on 27th June 2026. Please ensure all timesheets and leave applications are submitted by 24th June.', 'urgent', None),
            ('Public Holiday – Madaraka Day', '1st June 2026 is a public holiday. All offices will be closed. Blue-collar staff on shift duty will receive holiday pay.', 'normal', None),
            ('Annual Medical Camp – July 2026', 'The company will be hosting a free medical camp on 15th July 2026 at the Upperhill office. All employees are encouraged to attend.', 'normal', timezone.now() + datetime.timedelta(days=30)),
            ('Fire Drill – 10th July 2026', 'A mandatory fire drill will be held on 10th July 2026 at 10:00 AM. Please familiarise yourself with the evacuation routes.', 'urgent', timezone.now() + datetime.timedelta(days=18)),
            ('Updated HR Policy Handbook', 'The HR Policy Handbook has been updated. Please download the latest version from the HR portal and acknowledge receipt by 30th June 2026.', 'normal', None),
        ]
        for title, body, priority, expires_at in anns:
            Announcement.objects.get_or_create(
                company_id=COMPANY_ID, title=title,
                defaults=dict(
                    tenant_id=TENANT_ID, body=body,
                    priority=priority, created_by=hr_uid,
                    expires_at=expires_at,
                )
            )
        self.stdout.write('  announcements: done')

    # ────────────────────────────────────────────────────────────────────────
    # RECRUITMENT  (Careers site + Dashboard)
    # ────────────────────────────────────────────────────────────────────────
    def _recruitment(self):
        from apps.recruitment.models import JobPosting, Candidate, JobAlert, JobAlertLog
        from apps.hr.models import BackgroundCheck
        hr_uid = uuid.UUID('a1b2c3d4-0003-0003-0003-000000000010')
        today = datetime.date.today()

        job_specs = [
            (uuid.UUID('a1b2c3d4-0008-0008-0008-000000000001'),
             'Senior Python Developer', 'Engineering', 'open', 'white_collar',
             ['Python','Django','PostgreSQL','REST API','Docker'], today + datetime.timedelta(days=30), 'mid'),
            (uuid.UUID('a1b2c3d4-0008-0008-0008-000000000002'),
             'Sales & Business Development Manager', 'Sales', 'open', 'white_collar',
             ['Sales','B2B','CRM','Negotiation','Kenya market'], today + datetime.timedelta(days=21), 'senior'),
            (uuid.UUID('a1b2c3d4-0008-0008-0008-000000000003'),
             'Warehouse & Logistics Coordinator', 'Operations', 'open', 'casual',
             ['Forklift','Inventory','Logistics','ERP'], today + datetime.timedelta(days=14), 'entry'),
            (uuid.UUID('a1b2c3d4-0008-0008-0008-000000000004'),
             'HR Business Partner', 'Human Resources', 'on_hold', 'white_collar',
             ['HRBP','Kenyan labour law','HRIS','Talent management'], today - datetime.timedelta(days=5), 'mid'),
        ]
        job_objs = {}
        for jid, title, dept, status, etype, keywords, closing, exp in job_specs:
            jp, _ = JobPosting.objects.get_or_create(
                id=jid,
                defaults=dict(
                    tenant_id=TENANT_ID, company_id=COMPANY_ID,
                    title=title, department=dept, status=status,
                    employment_type=etype, required_keywords=keywords,
                    closing_date=closing, created_by=hr_uid,
                    location_name='Nairobi, Kenya', experience_level=exp,
                    description=f'We are looking for a talented {title} to join the Sheer Logic team. '
                                f'You will work closely with the {dept} department to deliver results.',
                )
            )
            job_objs[jid] = jp

        candidates = [
            # (job_idx, name, email, phone, score, stage, ai_skills)
            (0,'Brian Waweru','brian.waweru@gmail.com','+254701000001',88.5,'interview_l2',['Python','Django','Docker']),
            (0,'Eunice Muthoni','eunice.muthoni@gmail.com','+254702000002',76.0,'interview_l1',['Python','Flask','MySQL']),
            (0,'Kevin Ochieng','kevin.ochieng@gmail.com','+254703000003',91.2,'offer_sent',['Python','Django','PostgreSQL','Kubernetes']),
            (0,'Sharon Wambui','sharon.wambui@gmail.com','+254704000004',55.0,'rejected',['Python','PHP']),
            (1,'Tom Kariuki','tom.kariuki@gmail.com','+254705000005',82.0,'interview_l1',['Sales','B2B','CRM']),
            (1,'Agnes Mutindi','agnes.mutindi@gmail.com','+254706000006',79.5,'screened',['Sales','Retail']),
            (1,'Dennis Ouma','dennis.ouma@gmail.com','+254707000007',88.0,'interview_l2',['Sales','B2B','Negotiation']),
            (2,'Joseph Kamau','joseph.kamau@gmail.com','+254708000008',70.0,'screened',['Logistics','Inventory']),
            (2,'Alice Nyambura','alice.nyambura@gmail.com','+254709000009',65.0,'screened',['Forklift','ERP']),
            (3,'Ruth Chebet','ruth.chebet@gmail.com','+254710000010',93.0,'screened',['HRBP','Kenyan labour law','HRIS']),
            (3,'Paul Njoroge','paul.njoroge@gmail.com','+254711000011',87.5,'screened',['HR','Talent management']),
        ]
        job_list = [job_objs[s[0]] for s in job_specs]
        cand_objs = []
        for jidx, name, email, phone, score, stage, skills in candidates:
            cand, _ = Candidate.objects.get_or_create(
                job_posting=job_list[jidx], email=email,
                defaults=dict(
                    tenant_id=TENANT_ID, company_id=COMPANY_ID,
                    full_name=name, phone=phone,
                    ai_score=score, current_stage=stage,
                    ai_extracted_skills=skills, data_consent=True,
                    consent_at=timezone.now() - datetime.timedelta(days=random.randint(1,20)),
                    ai_summary=f'Candidate has {round(score/10, 0)*1} years of relevant experience with strong {skills[0]} skills.',
                    source='careers_site',
                )
            )
            cand_objs.append(cand)

        # Background checks for two top candidates
        for cand in cand_objs[:2]:
            BackgroundCheck.objects.get_or_create(
                company_id=COMPANY_ID, candidate_id=cand.id,
                check_type='criminal',
                defaults=dict(
                    tenant_id=TENANT_ID, status='pending',
                    requested_by=hr_uid,
                )
            )

        # Job alerts
        alerts_specs = [
            ('Tech Talent Alert','techjobs@example.com','+254720000001',['Python','Django'],'instant'),
            ('Sales Alert','salesjobs@example.com','+254720000002',['Sales','B2B'],'daily'),
        ]
        for name, email, phone, kws, freq in alerts_specs:
            alert, _ = JobAlert.objects.get_or_create(
                email=email,
                defaults=dict(
                    tenant_id=TENANT_ID, company_id=COMPANY_ID,
                    name=name, phone=phone, keywords=kws,
                    frequency=freq, is_active=True,
                )
            )
            JobAlertLog.objects.get_or_create(
                alert=alert, job_posting=job_list[0],
                defaults=dict(channel='email', status='sent')
            )
        self.stdout.write('  recruitment: done')

    # ────────────────────────────────────────────────────────────────────────
    # NOTIFICATION TEMPLATES
    # ────────────────────────────────────────────────────────────────────────
    def _notification_templates(self):
        from apps.core.models import NotificationTemplate
        templates = [
            (None,'leave.requested','email','New Leave Request – {employee_name}',
             'Hi {manager_name},\n\n{employee_name} has submitted a {leave_type} leave request from {start_date} to {end_date} ({days} days).\n\nPlease review and approve or reject in the HR Dashboard.\n\nRegards,\nSheer Logic HR'),
            (None,'leave.requested','sms','',
             'HR Alert: {employee_name} requests {leave_type} leave {start_date}→{end_date}. Approve: {approve_link}'),
            (None,'leave.approved','email','Your Leave Has Been Approved',
             'Hi {employee_name},\n\nYour {leave_type} leave from {start_date} to {end_date} has been approved.\n\nEnjoy your time off!\n\nSheer Logic HR'),
            (None,'leave.rejected','email','Leave Request Update',
             'Hi {employee_name},\n\nYour {leave_type} leave request from {start_date} to {end_date} could not be approved at this time.\n\nReason: {rejection_reason}\n\nPlease speak with your manager for more details.\n\nSheer Logic HR'),
            (None,'payroll.pending_approval','email','Payroll Run Awaiting Your Approval – {period}',
             'Hi {approver_name},\n\nThe {period} payroll run has been submitted and requires your approval.\n\nTotal Gross: KES {total_gross}\nTotal Net: KES {total_net}\nEmployees: {employee_count}\n\nApprove here: {approve_link}\n\nSheer Logic HR'),
            (None,'payroll.pending_approval','sms','',
             'Action needed: {period} payroll (KES {total_net} net) awaits your approval. Tap to approve: {approve_link}'),
            (None,'overtime.requested','email','Overtime Request – {employee_name}',
             'Hi {manager_name},\n\n{employee_name} has requested {hours} hours of overtime on {date}.\n\nPlease review and respond.\n\nSheer Logic HR'),
            (None,'certificate.expiring','email','Certificate Expiry Alert – {employee_name}',
             'Hi HR Team,\n\n{employee_name}\'s {certificate_name} expires on {expiry_date} ({days_remaining} days remaining).\n\nPlease arrange for renewal.\n\nSheer Logic HR'),
            (None,'attendance.violation','email','Geofence Violation Alert',
             'Hi {manager_name},\n\n{employee_name} was detected outside the {zone_name} geofence zone at {time}.\n\nDistance: {distance_m}m from boundary.\n\nPlease follow up.\n\nSheer Logic HR'),
            (None,'onboarding.document_missing','email','Onboarding Documents Required – {employee_name}',
             'Hi {employee_name},\n\nWelcome to Sheer Logic! To complete your onboarding, please submit the following documents:\n\n{missing_documents}\n\nPlease upload via the HR portal or deliver to the HR office.\n\nSheer Logic HR'),
        ]
        for company_id_val, event, channel, subject, body in templates:
            NotificationTemplate.objects.get_or_create(
                company_id=company_id_val, event=event, channel=channel,
                defaults=dict(subject=subject, body=body, is_active=True)
            )
        self.stdout.write('  notification templates: done')

    # ────────────────────────────────────────────────────────────────────────
    # AUDIT LOG  (a handful of entries so the audit trail page isn't empty)
    # ────────────────────────────────────────────────────────────────────────
    def _audit_log(self):
        from apps.core.models import ServiceAuditLog
        hr_uid = uuid.UUID('a1b2c3d4-0003-0003-0003-000000000010')
        entries = [
            ('payroll.submitted',  'PayrollRun', str(uuid.UUID('a1b2c3d4-0006-0006-0006-000000000001')), {'period':'May 2026'}),
            ('payroll.approved',   'PayrollRun', str(uuid.UUID('a1b2c3d4-0006-0006-0006-000000000001')), {'decision':'approved'}),
            ('payroll.paid',       'PayrollRun', str(uuid.UUID('a1b2c3d4-0006-0006-0006-000000000001')), {'method':'mpesa+bank'}),
            ('leave.approved',     'LeaveRequest', 'demo-leave-001', {'leave_type':'annual'}),
            ('employee.created',   'EmployeeProfile', 'SL-001', {'name':'Grace Wanjiku'}),
            ('rbac.grant',         'RolePermission', 'payroll.manage', {'role':'internal_hr'}),
            ('background_check.completed','BackgroundCheck','demo-bgc-001',{'verdict':'clean'}),
        ]
        for action, obj_type, obj_id, meta in entries:
            if not ServiceAuditLog.objects.filter(
                company_id=COMPANY_ID, action=action, object_id=obj_id
            ).exists():
                ServiceAuditLog.objects.create(
                    company_id=COMPANY_ID, tenant_id=TENANT_ID,
                    actor_user_id=hr_uid, actor_label='carol.njeri@sheerlogic.co.ke',
                    action=action, object_type=obj_type, object_id=obj_id,
                    metadata=meta,
                )
        self.stdout.write('  audit log: done')
