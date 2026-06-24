import uuid
from datetime import date

from django.contrib.auth.models import User
from django.test import override_settings
from rest_framework.test import APIClient, APITestCase

from apps.performance.models import (Competency, CompetencyRating,
                                      DevelopmentPlan, DevelopmentPlanItem,
                                      FeedbackRequest, FeedbackResponse,
                                      GoalUpdate, PerformanceGoal)

COMPANY = uuid.UUID('00000000-0000-0000-0000-000000000095')
COMPANY_STR = str(COMPANY)


def _goal(**kwargs):
    defaults = dict(
        company_id=COMPANY, tenant_id=uuid.uuid4(),
        employee_id=uuid.uuid4(), title='Grow Revenue',
        category='okr', status='active', period_year=2026,
        target_value=100.0, current_value=0.0,
    )
    defaults.update(kwargs)
    return PerformanceGoal.objects.create(**defaults)


def _competency(**kwargs):
    defaults = dict(
        company_id=COMPANY, tenant_id=uuid.uuid4(),
        name=f'Communication {uuid.uuid4().hex[:4]}',
        category='behavioural',
    )
    defaults.update(kwargs)
    return Competency.objects.create(**defaults)


def _plan(**kwargs):
    defaults = dict(
        company_id=COMPANY, tenant_id=uuid.uuid4(),
        employee_id=uuid.uuid4(), title='IDP 2026', period_year=2026,
    )
    defaults.update(kwargs)
    return DevelopmentPlan.objects.create(**defaults)


def _feedback_request(subject_id=None, **kwargs):
    defaults = dict(
        company_id=COMPANY, tenant_id=uuid.uuid4(),
        subject_id=subject_id or uuid.uuid4(),
        requester_id=uuid.uuid4(),
        review_cycle='2026-H1',
        status='open', is_anonymous=True,
    )
    defaults.update(kwargs)
    return FeedbackRequest.objects.create(**defaults)


@override_settings(RBAC_STRICT=False)
class TestGoalCRUD(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user('perf_test1', password='pass')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.client.credentials(
            HTTP_X_COMPANY_ID=COMPANY_STR,
            HTTP_X_USER_ROLE='internal_hr',
        )
        self.emp_id = uuid.uuid4()

    def test_create_goal(self):
        resp = self.client.post('/api/performance/goals/', {
            'employee_id': str(self.emp_id),
            'title': 'Close 10 deals',
            'category': 'kpi',
            'period_year': 2026,
            'target_value': 10,
        })
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()['title'], 'Close 10 deals')

    def test_list_goals(self):
        _goal(employee_id=self.emp_id)
        _goal(employee_id=self.emp_id)
        resp = self.client.get('/api/performance/goals/')
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(len(resp.json()['results']), 2)

    def test_filter_goals_by_employee(self):
        other_id = uuid.uuid4()
        _goal(employee_id=self.emp_id)
        _goal(employee_id=other_id)
        resp = self.client.get(f'/api/performance/goals/?employee_id={self.emp_id}')
        results = resp.json()['results']
        self.assertTrue(all(r['employee_id'] == str(self.emp_id) for r in results))

    def test_filter_goals_by_status(self):
        _goal(employee_id=self.emp_id, status='active')
        _goal(employee_id=self.emp_id, status='completed')
        resp = self.client.get('/api/performance/goals/?status=completed')
        results = resp.json()['results']
        self.assertTrue(all(r['status'] == 'completed' for r in results))

    def test_goal_detail_includes_updates(self):
        goal = _goal(employee_id=self.emp_id)
        resp = self.client.get(f'/api/performance/goals/{goal.id}/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('updates', resp.json())
        self.assertIn('progress_pct', resp.json())

    def test_update_goal(self):
        goal = _goal(employee_id=self.emp_id, status='draft')
        resp = self.client.patch(f'/api/performance/goals/{goal.id}/',
                                 {'status': 'active'})
        self.assertEqual(resp.status_code, 200)

    def test_soft_delete_goal(self):
        goal = _goal(employee_id=self.emp_id)
        resp = self.client.delete(f'/api/performance/goals/{goal.id}/')
        self.assertEqual(resp.status_code, 204)
        goal.refresh_from_db()
        self.assertTrue(goal.is_deleted)


@override_settings(RBAC_STRICT=False)
class TestGoalUpdate(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user('perf_test2', password='pass')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.client.credentials(
            HTTP_X_COMPANY_ID=COMPANY_STR,
            HTTP_X_USER_ROLE='internal_hr',
        )
        self.goal = _goal()

    def test_add_check_in(self):
        resp = self.client.post(
            f'/api/performance/goals/{self.goal.id}/updates/',
            {'progress_pct': 25, 'note': 'Q1 done'})
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()['progress_pct'], 25)

    def test_check_in_syncs_current_value(self):
        self.client.post(
            f'/api/performance/goals/{self.goal.id}/updates/',
            {'progress_pct': 50, 'current_value': 50.0, 'note': 'midpoint'})
        self.goal.refresh_from_db()
        self.assertEqual(self.goal.current_value, 50.0)

    def test_list_updates(self):
        GoalUpdate.objects.create(
            company_id=COMPANY, tenant_id=uuid.uuid4(),
            goal=self.goal, progress_pct=20, note='first')
        GoalUpdate.objects.create(
            company_id=COMPANY, tenant_id=uuid.uuid4(),
            goal=self.goal, progress_pct=40, note='second')
        resp = self.client.get(f'/api/performance/goals/{self.goal.id}/updates/')
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(len(resp.json()), 2)

    def test_progress_pct_from_target(self):
        self.goal.target_value = 100
        self.goal.current_value = 75
        self.goal.save()
        resp = self.client.get(f'/api/performance/goals/{self.goal.id}/')
        self.assertEqual(resp.json()['progress_pct'], 75.0)


@override_settings(RBAC_STRICT=False)
class TestCompetency(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user('perf_test3', password='pass')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.client.credentials(
            HTTP_X_COMPANY_ID=COMPANY_STR,
            HTTP_X_USER_ROLE='internal_hr',
        )

    def test_create_competency(self):
        resp = self.client.post('/api/performance/competencies/', {
            'name': 'Python', 'category': 'technical'})
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()['name'], 'Python')

    def test_list_competencies(self):
        _competency()
        _competency()
        resp = self.client.get('/api/performance/competencies/')
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(len(resp.json()['results']), 2)

    def test_update_competency(self):
        comp = _competency()
        resp = self.client.patch(f'/api/performance/competencies/{comp.id}/',
                                 {'is_active': False})
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()['is_active'])

    def test_soft_delete_competency(self):
        comp = _competency()
        resp = self.client.delete(f'/api/performance/competencies/{comp.id}/')
        self.assertEqual(resp.status_code, 204)
        comp.refresh_from_db()
        self.assertTrue(comp.is_deleted)

    def test_active_only_filter(self):
        _competency(is_active=True)
        _competency(is_active=False)
        resp = self.client.get('/api/performance/competencies/?active_only=1')
        data = resp.json()['results']
        self.assertTrue(all(r['is_active'] for r in data))


@override_settings(RBAC_STRICT=False)
class TestCompetencyRating(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user('perf_test4', password='pass')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.client.credentials(
            HTTP_X_COMPANY_ID=COMPANY_STR,
            HTTP_X_USER_ROLE='internal_hr',
        )
        self.comp = _competency()
        self.emp_id = uuid.uuid4()

    def test_create_rating(self):
        resp = self.client.post('/api/performance/competency-ratings/', {
            'employee_id': str(self.emp_id),
            'competency': str(self.comp.id),
            'rating': 4,
            'review_cycle': '2026-H1',
        })
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()['rating'], 4)

    def test_rating_includes_competency_name(self):
        resp = self.client.post('/api/performance/competency-ratings/', {
            'employee_id': str(self.emp_id),
            'competency': str(self.comp.id),
            'rating': 3,
            'review_cycle': '2026-H2',
        })
        self.assertIn('competency_name', resp.json())

    def test_filter_by_employee(self):
        other_id = uuid.uuid4()
        CompetencyRating.objects.create(
            company_id=COMPANY, tenant_id=uuid.uuid4(),
            employee_id=self.emp_id, competency=self.comp,
            rating=3, review_cycle='2026-H1')
        CompetencyRating.objects.create(
            company_id=COMPANY, tenant_id=uuid.uuid4(),
            employee_id=other_id, competency=self.comp,
            rating=4, review_cycle='2026-H1')
        resp = self.client.get(
            f'/api/performance/competency-ratings/?employee_id={self.emp_id}')
        results = resp.json()['results']
        self.assertTrue(all(r['employee_id'] == str(self.emp_id) for r in results))

    def test_filter_by_cycle(self):
        CompetencyRating.objects.create(
            company_id=COMPANY, tenant_id=uuid.uuid4(),
            employee_id=self.emp_id, competency=self.comp,
            rating=3, review_cycle='2025-H2')
        CompetencyRating.objects.create(
            company_id=COMPANY, tenant_id=uuid.uuid4(),
            employee_id=self.emp_id, competency=self.comp,
            rating=4, review_cycle='2026-H1')
        resp = self.client.get('/api/performance/competency-ratings/?cycle=2025-H2')
        results = resp.json()['results']
        self.assertTrue(all(r['review_cycle'] == '2025-H2' for r in results))

    def test_list_ratings(self):
        CompetencyRating.objects.create(
            company_id=COMPANY, tenant_id=uuid.uuid4(),
            employee_id=self.emp_id, competency=self.comp,
            rating=5, review_cycle='2026-H1')
        resp = self.client.get('/api/performance/competency-ratings/')
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(len(resp.json()['results']), 1)


@override_settings(RBAC_STRICT=False)
class TestDevelopmentPlan(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user('perf_test5', password='pass')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.client.credentials(
            HTTP_X_COMPANY_ID=COMPANY_STR,
            HTTP_X_USER_ROLE='internal_hr',
        )
        self.emp_id = uuid.uuid4()

    def test_create_plan(self):
        resp = self.client.post('/api/performance/development-plans/', {
            'employee_id': str(self.emp_id),
            'title': 'IDP 2026', 'period_year': 2026,
        })
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()['title'], 'IDP 2026')

    def test_list_plans(self):
        _plan(employee_id=self.emp_id)
        _plan(employee_id=self.emp_id)
        resp = self.client.get('/api/performance/development-plans/')
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(len(resp.json()['results']), 2)

    def test_plan_detail_includes_items(self):
        plan = _plan(employee_id=self.emp_id)
        resp = self.client.get(f'/api/performance/development-plans/{plan.id}/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('items', resp.json())
        self.assertIn('item_count', resp.json())

    def test_add_item_to_plan(self):
        plan = _plan(employee_id=self.emp_id)
        resp = self.client.post(
            f'/api/performance/development-plans/{plan.id}/items/',
            {'item_type': 'action', 'title': 'Read Clean Code', 'order': 0})
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()['title'], 'Read Clean Code')

    def test_mark_item_done(self):
        plan = _plan(employee_id=self.emp_id)
        item = DevelopmentPlanItem.objects.create(
            company_id=COMPANY, tenant_id=uuid.uuid4(),
            plan=plan, item_type='action', title='Do X', order=0)
        resp = self.client.patch(
            f'/api/performance/plan-items/{item.id}/', {'is_done': True})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['is_done'])

    def test_soft_delete_plan(self):
        plan = _plan(employee_id=self.emp_id)
        resp = self.client.delete(
            f'/api/performance/development-plans/{plan.id}/')
        self.assertEqual(resp.status_code, 204)
        plan.refresh_from_db()
        self.assertTrue(plan.is_deleted)


@override_settings(RBAC_STRICT=False)
class TestFeedbackRequest(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user('perf_test6', password='pass')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.client.credentials(
            HTTP_X_COMPANY_ID=COMPANY_STR,
            HTTP_X_USER_ROLE='internal_hr',
        )
        self.subject_id = uuid.uuid4()
        self.requester_id = uuid.uuid4()

    def test_create_feedback_request(self):
        resp = self.client.post('/api/performance/feedback-requests/', {
            'subject_id': str(self.subject_id),
            'requester_id': str(self.requester_id),
            'review_cycle': '2026-H1',
            'is_anonymous': True,
        })
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()['review_cycle'], '2026-H1')

    def test_list_feedback_requests(self):
        _feedback_request(subject_id=self.subject_id)
        _feedback_request(subject_id=self.subject_id)
        resp = self.client.get('/api/performance/feedback-requests/')
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(len(resp.json()['results']), 2)

    def test_retrieve_feedback_request(self):
        fr = _feedback_request(subject_id=self.subject_id)
        resp = self.client.get(f'/api/performance/feedback-requests/{fr.id}/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('response_count', resp.json())

    def test_close_feedback_request(self):
        fr = _feedback_request(subject_id=self.subject_id)
        resp = self.client.post(
            f'/api/performance/feedback-requests/{fr.id}/close/', {})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['status'], 'closed')

    def test_filter_by_subject(self):
        _feedback_request(subject_id=self.subject_id)
        _feedback_request()  # different subject
        resp = self.client.get(
            f'/api/performance/feedback-requests/?subject_id={self.subject_id}')
        results = resp.json()['results']
        self.assertTrue(
            all(r['subject_id'] == str(self.subject_id) for r in results))

    def test_response_count_increments(self):
        fr = _feedback_request(subject_id=self.subject_id)
        FeedbackResponse.objects.create(
            company_id=COMPANY, tenant_id=uuid.uuid4(),
            request=fr, reviewer_id=uuid.uuid4(),
            overall_rating=4, submitted_at=None)
        resp = self.client.get(f'/api/performance/feedback-requests/{fr.id}/')
        self.assertEqual(resp.json()['response_count'], 1)


@override_settings(RBAC_STRICT=False)
class TestFeedbackResponse(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user('perf_test7', password='pass')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.client.credentials(
            HTTP_X_COMPANY_ID=COMPANY_STR,
            HTTP_X_USER_ROLE='internal_hr',
        )
        self.fr = _feedback_request()
        self.reviewer_id = uuid.uuid4()

    def _respond(self, reviewer_id=None, rating=4, fr=None):
        fr = fr or self.fr
        reviewer_id = reviewer_id or self.reviewer_id
        return self.client.post(
            f'/api/performance/feedback-requests/{fr.id}/respond/',
            {
                'reviewer_id': str(reviewer_id),
                'overall_rating': rating,
                'strengths': 'Great communicator',
                'improvements': 'Needs delegation',
                'answers': {},
            },
            format='json')

    def test_submit_response(self):
        resp = self._respond()
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()['overall_rating'], 4)

    def test_duplicate_reviewer_rejected(self):
        self._respond()
        resp = self._respond()  # same reviewer_id
        self.assertEqual(resp.status_code, 409)

    def test_respond_to_closed_request_rejected(self):
        self.fr.status = 'closed'
        self.fr.save()
        resp = self._respond()
        self.assertEqual(resp.status_code, 409)

    def test_anonymous_responses_hide_reviewer(self):
        self._respond()
        resp = self.client.get(
            f'/api/performance/feedback-requests/{self.fr.id}/responses/')
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.json()[0]['reviewer_id'])

    def test_non_anonymous_shows_reviewer(self):
        fr = _feedback_request(is_anonymous=False)
        reviewer_id = uuid.uuid4()
        self._respond(reviewer_id=reviewer_id, fr=fr)
        resp = self.client.get(
            f'/api/performance/feedback-requests/{fr.id}/responses/')
        self.assertEqual(str(reviewer_id), resp.json()[0]['reviewer_id'])

    def test_avg_rating_computed(self):
        fr = _feedback_request()
        FeedbackResponse.objects.create(
            company_id=COMPANY, tenant_id=uuid.uuid4(),
            request=fr, reviewer_id=uuid.uuid4(),
            overall_rating=4, submitted_at=None)
        FeedbackResponse.objects.create(
            company_id=COMPANY, tenant_id=uuid.uuid4(),
            request=fr, reviewer_id=uuid.uuid4(),
            overall_rating=2, submitted_at=None)
        resp = self.client.get(f'/api/performance/feedback-requests/{fr.id}/')
        self.assertEqual(resp.json()['avg_rating'], 3.0)
