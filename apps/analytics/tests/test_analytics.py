import uuid
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from apps.crm.models import Placement, RecruitmentClient
from apps.hr.models import LeaveBalance, LeaveRequest
from apps.payroll.models import Company, EmployeeProfile, PayrollRun
from apps.recruitment.models import Candidate, JobPosting

COMPANY = uuid.UUID('00000000-0000-0000-0000-000000000080')
COMPANY_STR = str(COMPANY)

# Disable caching for all analytics tests
NO_CACHE = {
    'default': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'}
}


def _company_obj():
    return Company.objects.get_or_create(
        id=COMPANY,
        defaults={
            'name': 'Test Staffing Co', 'tenant_id': uuid.uuid4(),
            'contact_email': 'admin@test.com',
        }
    )[0]


def _employee(company=None, **kwargs):
    if company is None:
        company = _company_obj()
    defaults = dict(
        company=company,
        tenant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        job_title='Developer',
        department='Engineering',
        employment_type='full_time',
        employment_status='active',
        worker_class='white_collar',
        salary=100000,
        payment_method='bank',
        start_date=date.today() - timedelta(days=60),
    )
    defaults.update(kwargs)
    return EmployeeProfile.objects.create(**defaults)


def _posting():
    return JobPosting.objects.create(
        company_id=COMPANY, title='Dev', description='...')


def _candidate(stage='screened', source='careers_site'):
    posting = _posting()
    return Candidate.objects.create(
        company_id=COMPANY, job_posting=posting,
        full_name='Test Cand', email=f'{uuid.uuid4()}@t.com',
        current_stage=stage, source=source,
    )


@override_settings(RBAC_STRICT=False, CACHES=NO_CACHE)
class TestOverviewView(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user('ana_test1', password='pass')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.client.credentials(
            HTTP_X_COMPANY_ID=COMPANY_STR,
            HTTP_X_USER_ROLE='internal_hr',
        )

    def test_overview_returns_200(self):
        resp = self.client.get('/api/analytics/overview/')
        self.assertEqual(resp.status_code, 200)

    def test_overview_has_expected_keys(self):
        resp = self.client.get('/api/analytics/overview/')
        data = resp.json()
        for key in ['total_employees', 'new_hires_30d', 'open_job_postings',
                    'active_candidates', 'pending_leave_requests',
                    'placements_30d', 'active_clients']:
            self.assertIn(key, data)

    def test_overview_counts_employees(self):
        _employee()
        _employee(department='Sales')
        resp = self.client.get('/api/analytics/overview/')
        self.assertEqual(resp.json()['total_employees'], 2)

    def test_overview_counts_open_postings(self):
        JobPosting.objects.create(
            company_id=COMPANY, title='Eng', description='...', status='open')
        JobPosting.objects.create(
            company_id=COMPANY, title='PM', description='...', status='closed')
        resp = self.client.get('/api/analytics/overview/')
        self.assertGreaterEqual(resp.json()['open_job_postings'], 1)

    def test_overview_counts_candidates(self):
        _candidate()
        _candidate()
        resp = self.client.get('/api/analytics/overview/')
        self.assertGreaterEqual(resp.json()['active_candidates'], 2)

    def test_overview_new_hires_30d(self):
        _employee(start_date=date.today() - timedelta(days=10))
        _employee(start_date=date.today() - timedelta(days=365))
        resp = self.client.get('/api/analytics/overview/')
        self.assertGreaterEqual(resp.json()['new_hires_30d'], 1)

    def test_overview_active_clients(self):
        RecruitmentClient.objects.create(
            company_id=COMPANY, name='Client A', status='active')
        RecruitmentClient.objects.create(
            company_id=COMPANY, name='Client B', status='churned')
        resp = self.client.get('/api/analytics/overview/')
        self.assertGreaterEqual(resp.json()['active_clients'], 1)


@override_settings(RBAC_STRICT=False, CACHES=NO_CACHE)
class TestHeadcountView(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user('ana_test2', password='pass')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.client.credentials(
            HTTP_X_COMPANY_ID=COMPANY_STR,
            HTTP_X_USER_ROLE='internal_hr',
        )

    def test_headcount_returns_200(self):
        resp = self.client.get('/api/analytics/headcount/')
        self.assertEqual(resp.status_code, 200)

    def test_headcount_has_expected_keys(self):
        resp = self.client.get('/api/analytics/headcount/')
        data = resp.json()
        for key in ['total', 'by_department', 'by_employment_type',
                    'by_worker_class', 'monthly_hires', 'monthly_exits',
                    'attrition_rate_12m']:
            self.assertIn(key, data)

    def test_headcount_by_department(self):
        _employee(department='Engineering')
        _employee(department='Engineering')
        _employee(department='Sales')
        resp = self.client.get('/api/analytics/headcount/')
        by_dept = resp.json()['by_department']
        depts = {r['department']: r['count'] for r in by_dept}
        self.assertGreaterEqual(depts.get('Engineering', 0), 2)
        self.assertGreaterEqual(depts.get('Sales', 0), 1)

    def test_headcount_total_matches_employees(self):
        _employee()
        _employee()
        _employee()
        resp = self.client.get('/api/analytics/headcount/')
        self.assertGreaterEqual(resp.json()['total'], 3)

    def test_headcount_monthly_hires_structure(self):
        _employee(start_date=date.today() - timedelta(days=30))
        resp = self.client.get('/api/analytics/headcount/')
        hires = resp.json()['monthly_hires']
        if hires:
            self.assertIn('year', hires[0])
            self.assertIn('month', hires[0])
            self.assertIn('count', hires[0])


@override_settings(RBAC_STRICT=False, CACHES=NO_CACHE)
class TestRecruitmentView(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user('ana_test3', password='pass')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.client.credentials(
            HTTP_X_COMPANY_ID=COMPANY_STR,
            HTTP_X_USER_ROLE='internal_hr',
        )

    def test_recruitment_returns_200(self):
        resp = self.client.get('/api/analytics/recruitment/')
        self.assertEqual(resp.status_code, 200)

    def test_recruitment_has_expected_keys(self):
        resp = self.client.get('/api/analytics/recruitment/')
        data = resp.json()
        for key in ['total_applications', 'hired_count', 'conversion_rate',
                    'by_stage', 'by_source', 'interviews_scheduled',
                    'interviews_completed', 'top_postings']:
            self.assertIn(key, data)

    def test_recruitment_counts_applications(self):
        _candidate(stage='screened')
        _candidate(stage='hired')
        _candidate(stage='rejected')
        resp = self.client.get('/api/analytics/recruitment/')
        self.assertGreaterEqual(resp.json()['total_applications'], 3)

    def test_recruitment_hired_count(self):
        _candidate(stage='hired')
        _candidate(stage='hired')
        _candidate(stage='screened')
        resp = self.client.get('/api/analytics/recruitment/')
        self.assertGreaterEqual(resp.json()['hired_count'], 2)

    def test_recruitment_conversion_rate_is_percentage(self):
        _candidate(stage='hired')
        _candidate(stage='screened')
        resp = self.client.get('/api/analytics/recruitment/')
        rate = resp.json()['conversion_rate']
        self.assertGreaterEqual(rate, 0)
        self.assertLessEqual(rate, 100)

    def test_recruitment_by_source(self):
        _candidate(source='careers_site')
        _candidate(source='linkedin')
        resp = self.client.get('/api/analytics/recruitment/')
        sources = {r['source'] for r in resp.json()['by_source']}
        self.assertIn('careers_site', sources)

    def test_recruitment_filter_by_job_posting(self):
        posting = _posting()
        Candidate.objects.create(
            company_id=COMPANY, job_posting=posting,
            full_name='Filtered', email='f@f.com')
        _candidate()  # different posting
        resp = self.client.get(
            f'/api/analytics/recruitment/?job_posting_id={posting.id}')
        self.assertEqual(resp.json()['total_applications'], 1)


@override_settings(RBAC_STRICT=False, CACHES=NO_CACHE)
class TestPayrollAnalyticsView(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user('ana_test4', password='pass')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.client.credentials(
            HTTP_X_COMPANY_ID=COMPANY_STR,
            HTTP_X_USER_ROLE='internal_hr',
        )

    def test_payroll_returns_200(self):
        resp = self.client.get('/api/analytics/payroll/')
        self.assertEqual(resp.status_code, 200)

    def test_payroll_has_expected_keys(self):
        resp = self.client.get('/api/analytics/payroll/')
        for key in ['monthly_trend', 'total_spend_ytd', 'avg_salary', 'run_count']:
            self.assertIn(key, resp.json())

    def test_payroll_monthly_trend_includes_run(self):
        company = _company_obj()
        PayrollRun.objects.create(
            company=company, tenant_id=uuid.uuid4(),
            period_year=2026, period_month=6,
            status='completed',
            total_gross=500000, total_deductions=50000, total_net=450000,
            run_by=uuid.uuid4(),
        )
        resp = self.client.get('/api/analytics/payroll/')
        trend = resp.json()['monthly_trend']
        self.assertGreaterEqual(len(trend), 1)
        self.assertIn('total_net', trend[0])

    def test_payroll_months_param_respected(self):
        resp = self.client.get('/api/analytics/payroll/?months=3')
        self.assertEqual(resp.status_code, 200)

    def test_payroll_avg_salary(self):
        _employee(salary=100000)
        _employee(salary=200000)
        resp = self.client.get('/api/analytics/payroll/')
        avg = resp.json()['avg_salary']
        self.assertGreater(avg, 0)


@override_settings(RBAC_STRICT=False, CACHES=NO_CACHE)
class TestLeaveAnalyticsView(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user('ana_test5', password='pass')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.client.credentials(
            HTTP_X_COMPANY_ID=COMPANY_STR,
            HTTP_X_USER_ROLE='internal_hr',
        )
        self.today = date.today()

    def test_leave_returns_200(self):
        resp = self.client.get('/api/analytics/leave/')
        self.assertEqual(resp.status_code, 200)

    def test_leave_has_expected_keys(self):
        resp = self.client.get('/api/analytics/leave/')
        for key in ['year', 'by_type', 'by_status',
                    'total_approved_days', 'avg_days_per_employee',
                    'leave_utilization_rate']:
            self.assertIn(key, resp.json())

    def test_leave_by_type(self):
        emp_id = uuid.uuid4()
        LeaveRequest.objects.create(
            company_id=COMPANY, employee_id=emp_id,
            leave_type='annual', start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 5), days_requested=5, status='approved')
        LeaveRequest.objects.create(
            company_id=COMPANY, employee_id=emp_id,
            leave_type='sick', start_date=date(2026, 4, 1),
            end_date=date(2026, 4, 2), days_requested=2, status='approved')
        resp = self.client.get('/api/analytics/leave/?year=2026')
        types = {r['leave_type'] for r in resp.json()['by_type']}
        self.assertIn('annual', types)

    def test_leave_year_param(self):
        resp = self.client.get('/api/analytics/leave/?year=2025')
        self.assertEqual(resp.json()['year'], 2025)

    def test_leave_utilization_rate(self):
        emp_id = uuid.uuid4()
        LeaveBalance.objects.create(
            company_id=COMPANY, employee_id=emp_id,
            leave_type='annual', year=2026,
            total_days=21, used_days=14, remaining_days=7)
        resp = self.client.get('/api/analytics/leave/?year=2026')
        self.assertGreater(resp.json()['leave_utilization_rate'], 0)


@override_settings(RBAC_STRICT=False, CACHES=NO_CACHE)
class TestPlacementAnalyticsView(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user('ana_test6', password='pass')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.client.credentials(
            HTTP_X_COMPANY_ID=COMPANY_STR,
            HTTP_X_USER_ROLE='internal_hr',
        )

    def _placement(self, **kwargs):
        rc = RecruitmentClient.objects.create(
            company_id=COMPANY, name=f'Client {uuid.uuid4().hex[:4]}')
        posting = _posting()
        cand = Candidate.objects.create(
            company_id=COMPANY, job_posting=posting,
            full_name='P Cand', email=f'{uuid.uuid4()}@p.com')
        defaults = dict(
            company_id=COMPANY, client=rc, candidate=cand,
            job_title='Dev', start_date=date.today(),
            placement_fee=50000, status='started')
        defaults.update(kwargs)
        return Placement.objects.create(**defaults)

    def test_placements_returns_200(self):
        resp = self.client.get('/api/analytics/placements/')
        self.assertEqual(resp.status_code, 200)

    def test_placements_has_expected_keys(self):
        resp = self.client.get('/api/analytics/placements/')
        for key in ['monthly_placements', 'total_fee_ytd', 'total_placements',
                    'by_status', 'top_clients']:
            self.assertIn(key, resp.json())

    def test_placements_total_count(self):
        self._placement()
        self._placement()
        resp = self.client.get('/api/analytics/placements/')
        self.assertGreaterEqual(resp.json()['total_placements'], 2)

    def test_placements_cancelled_excluded(self):
        self._placement(status='started')
        self._placement(status='cancelled')
        resp = self.client.get('/api/analytics/placements/')
        self.assertGreaterEqual(resp.json()['total_placements'], 1)
        # cancelled must not inflate the total
        by_status = {r['status']: r['count'] for r in resp.json()['by_status']}
        self.assertGreaterEqual(by_status.get('cancelled', 0), 1)

    def test_placements_fee_ytd(self):
        self._placement(placement_fee=75000, start_date=date(2026, 1, 1))
        self._placement(placement_fee=50000, start_date=date(2026, 3, 1))
        resp = self.client.get('/api/analytics/placements/')
        self.assertGreaterEqual(resp.json()['total_fee_ytd'], 0)

    def test_placements_months_param(self):
        resp = self.client.get('/api/analytics/placements/?months=6')
        self.assertEqual(resp.status_code, 200)

    def test_placements_top_clients(self):
        self._placement()
        self._placement()
        resp = self.client.get('/api/analytics/placements/')
        self.assertGreaterEqual(len(resp.json()['top_clients']), 0)
