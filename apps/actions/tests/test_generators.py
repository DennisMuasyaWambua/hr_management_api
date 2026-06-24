"""
Generator tests using Django TestCase + unittest.mock to avoid touching
other apps' real data. Each test creates minimal mock return values.
"""
import datetime
import uuid
from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.utils import timezone

from apps.actions.dataclasses import ActionCategory, ActionPriority
from apps.actions.generators.base import BaseActionGenerator


COMPANY_ID = uuid.UUID('00000000-0000-0000-0000-000000000001')


# ── BaseActionGenerator ──────────────────────────────────────────────────────

class TestBaseGenerator(TestCase):

    def test_make_id_format(self):
        result = BaseActionGenerator.make_id('recruitment', 'abc-123', 'INTERVIEW_OVERDUE')
        self.assertEqual(result, 'recruitment:abc-123:INTERVIEW_OVERDUE')

    def test_safe_generate_returns_empty_on_exception(self):
        class BrokenGenerator(BaseActionGenerator):
            category = 'recruitment'
            def generate(self):
                raise RuntimeError('DB is down')

        gen = BrokenGenerator(company_id=COMPANY_ID)
        result = gen.safe_generate()
        self.assertEqual(result, [])

    def test_safe_generate_returns_items_on_success(self):
        from apps.actions.dataclasses import ActionItem, ActionStatus

        class WorkingGenerator(BaseActionGenerator):
            category = 'recruitment'
            def generate(self):
                return [ActionItem(
                    id='test:abc:FOO',
                    action_type='FOO',
                    category=ActionCategory.RECRUITMENT,
                    priority=ActionPriority.LOW,
                    title='T', description='D',
                    source_module='test', source_record_id='abc',
                    action_url='/test/',
                )]

        gen = WorkingGenerator(company_id=COMPANY_ID)
        result = gen.safe_generate()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].action_type, 'FOO')


# ── RecruitmentActionGenerator ───────────────────────────────────────────────

class TestRecruitmentGenerator(TestCase):

    @patch('apps.actions.generators.recruitment.Interview')
    @patch('apps.actions.generators.recruitment.Candidate')
    @patch('apps.actions.generators.recruitment.JobPosting')
    def test_interview_overdue_generates_action(self, MockJP, MockCandidate, MockInterview):
        from apps.actions.generators.recruitment import RecruitmentActionGenerator

        now = timezone.now()
        past = now - datetime.timedelta(hours=50)
        mock_iv = MagicMock()
        mock_iv.id = uuid.uuid4()
        mock_iv.candidate.full_name = 'Jane Doe'
        mock_iv.candidate_id = uuid.uuid4()
        mock_iv.job_posting.title = 'Software Engineer'
        mock_iv.scheduled_at = past
        mock_iv.interview_type = 'l1'
        mock_iv.get_interview_type_display.return_value = 'Level 1'

        MockInterview.objects.filter.return_value.select_related.return_value = [mock_iv]
        MockCandidate.objects.filter.return_value.filter.return_value.values.return_value = []
        MockJP.objects.filter.return_value.values.return_value = []

        gen = RecruitmentActionGenerator(company_id=COMPANY_ID)
        items = gen.generate()

        overdue = [i for i in items if i.action_type == 'INTERVIEW_OVERDUE']
        self.assertEqual(len(overdue), 1)
        self.assertEqual(overdue[0].priority, ActionPriority.CRITICAL)

    @patch('apps.actions.generators.recruitment.Interview')
    @patch('apps.actions.generators.recruitment.Candidate')
    @patch('apps.actions.generators.recruitment.JobPosting')
    def test_pipeline_stalled_generates_medium_action(self, MockJP, MockCandidate, MockInterview):
        from apps.actions.generators.recruitment import RecruitmentActionGenerator

        now = timezone.now()
        MockInterview.objects.filter.return_value.select_related.return_value = []
        MockJP.objects.filter.return_value.values.return_value = []

        stale_ts = now - datetime.timedelta(days=20)
        MockCandidate.objects.filter.return_value.filter.return_value.values.return_value = [{
            'id': uuid.uuid4(),
            'full_name': 'John Smith',
            'current_stage': 'screened',
            'updated_at': stale_ts,
        }]

        gen = RecruitmentActionGenerator(company_id=COMPANY_ID)
        items = gen.generate()

        stalled = [i for i in items if i.action_type == 'PIPELINE_STALLED']
        self.assertEqual(len(stalled), 1)
        self.assertEqual(stalled[0].priority, ActionPriority.MEDIUM)

    @patch('apps.actions.generators.recruitment.Interview')
    @patch('apps.actions.generators.recruitment.Candidate')
    @patch('apps.actions.generators.recruitment.JobPosting')
    def test_job_closing_soon_generates_high_action(self, MockJP, MockCandidate, MockInterview):
        from apps.actions.generators.recruitment import RecruitmentActionGenerator

        MockInterview.objects.filter.return_value.select_related.return_value = []
        MockCandidate.objects.filter.return_value.filter.return_value.values.return_value = []
        today = timezone.now().date()
        MockJP.objects.filter.return_value.values.return_value = [{
            'id': uuid.uuid4(),
            'title': 'Backend Engineer',
            'closing_date': today + datetime.timedelta(days=2),
            'department': 'Engineering',
        }]

        gen = RecruitmentActionGenerator(company_id=COMPANY_ID)
        items = gen.generate()

        closing = [i for i in items if i.action_type == 'JOB_CLOSING_SOON']
        self.assertEqual(len(closing), 1)
        self.assertEqual(closing[0].priority, ActionPriority.HIGH)

    @patch('apps.actions.generators.recruitment.Interview')
    @patch('apps.actions.generators.recruitment.Candidate')
    @patch('apps.actions.generators.recruitment.JobPosting')
    def test_empty_db_returns_no_items(self, MockJP, MockCandidate, MockInterview):
        from apps.actions.generators.recruitment import RecruitmentActionGenerator

        MockInterview.objects.filter.return_value.select_related.return_value = []
        MockCandidate.objects.filter.return_value.filter.return_value.values.return_value = []
        MockJP.objects.filter.return_value.values.return_value = []

        gen = RecruitmentActionGenerator(company_id=COMPANY_ID)
        self.assertEqual(gen.generate(), [])


# ── LeaveActionGenerator ─────────────────────────────────────────────────────

class TestLeaveGenerator(TestCase):

    @patch('apps.actions.generators.leave.LeaveBalance')
    @patch('apps.actions.generators.leave.LeaveRecall')
    @patch('apps.actions.generators.leave.LeaveRequest')
    def test_pending_leave_generates_action(self, MockLR, MockRecall, MockBalance):
        from apps.actions.generators.leave import LeaveActionGenerator

        now = timezone.now()
        MockLR.objects.filter.return_value.values.return_value = [{
            'id': uuid.uuid4(),
            'employee_id': uuid.uuid4(),
            'leave_type': 'annual',
            'start_date': (now + datetime.timedelta(days=7)).date(),
            'end_date': (now + datetime.timedelta(days=14)).date(),
            'days_requested': 7,
            'created_at': now - datetime.timedelta(hours=10),
        }]
        MockRecall.objects.filter.return_value.values.return_value = []
        MockBalance.objects.filter.return_value.values.return_value = []

        gen = LeaveActionGenerator(company_id=COMPANY_ID)
        items = gen.generate()

        pending = [i for i in items if i.action_type == 'LEAVE_PENDING_APPROVAL']
        self.assertEqual(len(pending), 1)

    @patch('apps.actions.generators.leave.LeaveBalance')
    @patch('apps.actions.generators.leave.LeaveRecall')
    @patch('apps.actions.generators.leave.LeaveRequest')
    def test_low_balance_generates_low_priority(self, MockLR, MockRecall, MockBalance):
        from apps.actions.generators.leave import LeaveActionGenerator

        MockLR.objects.filter.return_value.values.return_value = []
        MockRecall.objects.filter.return_value.values.return_value = []
        MockBalance.objects.filter.return_value.values.return_value = [{
            'id': uuid.uuid4(),
            'employee_id': uuid.uuid4(),
            'remaining_days': 1,
            'total_days': 21,
            'updated_at': timezone.now(),
        }]

        gen = LeaveActionGenerator(company_id=COMPANY_ID)
        items = gen.generate()

        low = [i for i in items if i.action_type == 'LOW_LEAVE_BALANCE']
        self.assertEqual(len(low), 1)
        self.assertEqual(low[0].priority, ActionPriority.LOW)


# ── OffboardingActionGenerator ───────────────────────────────────────────────

class TestOffboardingGenerator(TestCase):

    @patch('apps.actions.generators.offboarding.EmployeeExit')
    def test_exit_overdue_generates_action(self, MockExit):
        from apps.actions.generators.offboarding import OffboardingActionGenerator

        today = timezone.now().date()
        mock_ex = MagicMock()
        mock_ex.id = uuid.uuid4()
        mock_ex.employee_id = uuid.uuid4()
        mock_ex.status = 'initiated'
        mock_ex.kind = 'resignation'
        mock_ex.last_working_day = today - datetime.timedelta(days=3)
        mock_ex.final_dues_paid_at = None
        mock_ex.updated_at = timezone.now() - datetime.timedelta(days=5)
        # No clearance record
        type(mock_ex).clearance = property(lambda self: (_ for _ in ()).throw(Exception('no clearance')))

        MockExit.objects.filter.return_value.select_related.return_value = [mock_ex]

        gen = OffboardingActionGenerator(company_id=COMPANY_ID)
        items = gen.generate()

        overdue = [i for i in items if i.action_type == 'EXIT_OVERDUE']
        self.assertEqual(len(overdue), 1)
        self.assertEqual(overdue[0].priority, ActionPriority.HIGH)


# ── ComplianceActionGenerator ────────────────────────────────────────────────

class TestComplianceGenerator(TestCase):

    @patch('apps.actions.generators.compliance.BackgroundCheck')
    @patch('apps.actions.generators.compliance.DisciplinaryRecord')
    @patch('apps.actions.generators.compliance.EmployeeCertificate')
    @patch('apps.actions.generators.compliance.ComplianceAlert')
    def test_flagged_bg_check_generates_critical(self, MockAlert, MockCert, MockDisc, MockBG):
        from apps.actions.generators.compliance import ComplianceActionGenerator

        MockAlert.objects.filter.return_value.values.return_value = []
        MockCert.objects.filter.return_value.values.return_value = []
        MockDisc.objects.filter.return_value.values.return_value = []
        MockBG.objects.filter.return_value.values.return_value = [{
            'id': uuid.uuid4(),
            'employee_id': uuid.uuid4(),
            'candidate_id': None,
            'check_type': 'criminal',
            'requested_at': timezone.now() - datetime.timedelta(days=5),
            'flags': ['previous_conviction'],
        }]

        gen = ComplianceActionGenerator(company_id=COMPANY_ID)
        items = gen.generate()

        flagged = [i for i in items if i.action_type == 'BACKGROUND_CHECK_FLAGGED']
        self.assertEqual(len(flagged), 1)
        self.assertEqual(flagged[0].priority, ActionPriority.CRITICAL)

    @patch('apps.actions.generators.compliance.BackgroundCheck')
    @patch('apps.actions.generators.compliance.DisciplinaryRecord')
    @patch('apps.actions.generators.compliance.EmployeeCertificate')
    @patch('apps.actions.generators.compliance.ComplianceAlert')
    def test_certificate_within_alert_window_generates_action(
        self, MockAlert, MockCert, MockDisc, MockBG
    ):
        from apps.actions.generators.compliance import ComplianceActionGenerator

        today = timezone.now().date()
        MockAlert.objects.filter.return_value.values.return_value = []
        MockDisc.objects.filter.return_value.values.return_value = []
        MockBG.objects.filter.return_value.values.return_value = []
        MockCert.objects.filter.return_value.values.return_value = [{
            'id': uuid.uuid4(),
            'employee_id': uuid.uuid4(),
            'name': 'Food Handler Certificate',
            'expiry_date': today + datetime.timedelta(days=5),
            'alert_days_before': 30,
        }]

        gen = ComplianceActionGenerator(company_id=COMPANY_ID)
        items = gen.generate()

        expiring = [i for i in items if i.action_type == 'CERTIFICATE_EXPIRING']
        self.assertEqual(len(expiring), 1)
