import uuid

from django.contrib.auth.models import User
from django.test import override_settings
from rest_framework.test import APIClient, APITestCase

from apps.matching.models import JobMatchScore
from apps.recruitment.models import Candidate, JobPosting

COMPANY = uuid.UUID('00000000-0000-0000-0000-000000000070')
COMPANY_STR = str(COMPANY)
OTHER = uuid.UUID('00000000-0000-0000-0000-000000000071')


def _posting(company_id=None, **kwargs):
    defaults = dict(
        company_id=company_id or COMPANY,
        title='Backend Engineer',
        description='Build APIs.',
        required_keywords=['python', 'django'],
        experience_level='senior',
        location_name='Nairobi',
    )
    defaults.update(kwargs)
    return JobPosting.objects.create(**defaults)


def _candidate(posting=None, company_id=None, **kwargs):
    if posting is None:
        posting = _posting(company_id=company_id or COMPANY)
    defaults = dict(
        company_id=company_id or COMPANY,
        job_posting=posting,
        full_name='Alice Dev',
        email='alice@dev.com',
        skills=['python', 'django'],
        experience_years=6,
        education_level='masters',
        location='Nairobi',
    )
    defaults.update(kwargs)
    return Candidate.objects.create(**defaults)


@override_settings(RBAC_STRICT=False)
class TestScoreView(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user('match_test1', password='pass')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.client.credentials(
            HTTP_X_COMPANY_ID=COMPANY_STR,
            HTTP_X_USER_ROLE='internal_hr',
        )
        self.posting = _posting()
        self.candidate = _candidate(posting=self.posting)

    def test_score_returns_200(self):
        resp = self.client.post('/api/matching/score/', {
            'candidate_id': str(self.candidate.id),
            'job_posting_id': str(self.posting.id),
        }, format='json')
        self.assertEqual(resp.status_code, 200)

    def test_score_returns_all_dimensions(self):
        resp = self.client.post('/api/matching/score/', {
            'candidate_id': str(self.candidate.id),
            'job_posting_id': str(self.posting.id),
        }, format='json')
        data = resp.json()
        self.assertIn('skill_score', data)
        self.assertIn('experience_score', data)
        self.assertIn('education_score', data)
        self.assertIn('location_score', data)
        self.assertIn('total_score', data)

    def test_score_persisted_to_db(self):
        self.client.post('/api/matching/score/', {
            'candidate_id': str(self.candidate.id),
            'job_posting_id': str(self.posting.id),
        }, format='json')
        self.assertTrue(
            JobMatchScore.objects.filter(
                candidate=self.candidate, job_posting=self.posting).exists())

    def test_score_updates_candidate_ai_score(self):
        self.client.post('/api/matching/score/', {
            'candidate_id': str(self.candidate.id),
            'job_posting_id': str(self.posting.id),
        }, format='json')
        self.candidate.refresh_from_db()
        self.assertIsNotNone(self.candidate.ai_score)

    def test_score_perfect_match(self):
        resp = self.client.post('/api/matching/score/', {
            'candidate_id': str(self.candidate.id),
            'job_posting_id': str(self.posting.id),
        }, format='json')
        self.assertGreater(resp.json()['total_score'], 80.0)

    def test_score_missing_fields_returns_400(self):
        resp = self.client.post('/api/matching/score/', {}, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_score_wrong_company_candidate_returns_404(self):
        other_posting = _posting(company_id=OTHER)
        other_candidate = _candidate(posting=other_posting, company_id=OTHER,
                                     email='x@x.com')
        resp = self.client.post('/api/matching/score/', {
            'candidate_id': str(other_candidate.id),
            'job_posting_id': str(self.posting.id),
        }, format='json')
        self.assertEqual(resp.status_code, 404)

    def test_score_rescore_updates_existing_row(self):
        self.client.post('/api/matching/score/', {
            'candidate_id': str(self.candidate.id),
            'job_posting_id': str(self.posting.id),
        }, format='json')
        self.client.post('/api/matching/score/', {
            'candidate_id': str(self.candidate.id),
            'job_posting_id': str(self.posting.id),
        }, format='json')
        count = JobMatchScore.objects.filter(
            candidate=self.candidate, job_posting=self.posting).count()
        self.assertEqual(count, 1)


@override_settings(RBAC_STRICT=False)
class TestScoreBulkView(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user('match_test2', password='pass')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.client.credentials(
            HTTP_X_COMPANY_ID=COMPANY_STR,
            HTTP_X_USER_ROLE='internal_hr',
        )
        self.posting = _posting()
        self.c1 = _candidate(posting=self.posting, full_name='Alice')
        self.c2 = _candidate(posting=self.posting, full_name='Bob',
                             email='bob@dev.com')

    def test_bulk_scores_all_candidates_for_posting(self):
        resp = self.client.post('/api/matching/score-bulk/', {
            'job_posting_id': str(self.posting.id),
        }, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['scored'], 2)

    def test_bulk_with_explicit_candidate_ids(self):
        resp = self.client.post('/api/matching/score-bulk/', {
            'job_posting_id': str(self.posting.id),
            'candidate_ids': [str(self.c1.id)],
        }, format='json')
        self.assertEqual(resp.json()['scored'], 1)

    def test_bulk_missing_job_returns_400(self):
        resp = self.client.post('/api/matching/score-bulk/', {}, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_bulk_persists_all_scores(self):
        self.client.post('/api/matching/score-bulk/', {
            'job_posting_id': str(self.posting.id),
        }, format='json')
        count = JobMatchScore.objects.filter(
            job_posting=self.posting, company_id=COMPANY).count()
        self.assertEqual(count, 2)


@override_settings(RBAC_STRICT=False)
class TestRankView(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user('match_test3', password='pass')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.client.credentials(
            HTTP_X_COMPANY_ID=COMPANY_STR,
            HTTP_X_USER_ROLE='internal_hr',
        )
        self.posting = _posting()

    def test_rank_returns_ordered_by_score(self):
        # Score a strong and weak candidate
        strong = _candidate(
            posting=self.posting, full_name='Strong', email='strong@dev.com',
            skills=['python', 'django'], experience_years=8,
            education_level='phd', location='Nairobi',
        )
        weak = _candidate(
            posting=self.posting, full_name='Weak', email='weak@dev.com',
            skills=[], experience_years=0, education_level='high_school',
            location='Mombasa',
        )
        self.client.post('/api/matching/score/', {
            'candidate_id': str(strong.id),
            'job_posting_id': str(self.posting.id),
        }, format='json')
        self.client.post('/api/matching/score/', {
            'candidate_id': str(weak.id),
            'job_posting_id': str(self.posting.id),
        }, format='json')

        resp = self.client.get(f'/api/matching/rank/{self.posting.id}/')
        self.assertEqual(resp.status_code, 200)
        results = resp.json()['results']
        self.assertGreaterEqual(len(results), 2)
        self.assertGreaterEqual(results[0]['total_score'], results[-1]['total_score'])
        self.assertEqual(results[0]['candidate_name'], 'Strong')

    def test_rank_other_company_404(self):
        other_posting = _posting(company_id=OTHER)
        resp = self.client.get(f'/api/matching/rank/{other_posting.id}/')
        self.assertEqual(resp.status_code, 404)

    def test_rank_empty_when_no_scores(self):
        resp = self.client.get(f'/api/matching/rank/{self.posting.id}/')
        self.assertEqual(resp.json()['count'], 0)


@override_settings(RBAC_STRICT=False)
class TestResultsView(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user('match_test4', password='pass')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.client.credentials(
            HTTP_X_COMPANY_ID=COMPANY_STR,
            HTTP_X_USER_ROLE='internal_hr',
        )
        self.posting = _posting()
        self.candidate = _candidate(posting=self.posting)

    def _score(self):
        self.client.post('/api/matching/score/', {
            'candidate_id': str(self.candidate.id),
            'job_posting_id': str(self.posting.id),
        }, format='json')

    def test_results_returns_200(self):
        self._score()
        resp = self.client.get('/api/matching/results/')
        self.assertEqual(resp.status_code, 200)

    def test_results_scoped_to_company(self):
        self._score()
        other_posting = _posting(company_id=OTHER)
        other_cand = _candidate(posting=other_posting, company_id=OTHER,
                                email='o@o.com')
        JobMatchScore.objects.create(
            company_id=OTHER, candidate=other_cand, job_posting=other_posting,
            total_score=50.0)
        resp = self.client.get('/api/matching/results/')
        for r in resp.json()['results']:
            self.assertEqual(r['company_id'], COMPANY_STR)

    def test_filter_by_candidate(self):
        self._score()
        c2 = _candidate(posting=self.posting, email='c2@dev.com', full_name='C2')
        JobMatchScore.objects.create(
            company_id=COMPANY, candidate=c2, job_posting=self.posting,
            total_score=40.0)
        resp = self.client.get(
            f'/api/matching/results/?candidate_id={self.candidate.id}')
        self.assertEqual(resp.json()['count'], 1)

    def test_filter_by_job_posting(self):
        self._score()
        p2 = _posting(title='Frontend Role')
        cand2 = _candidate(posting=p2, email='c3@dev.com', full_name='C3')
        JobMatchScore.objects.create(
            company_id=COMPANY, candidate=cand2, job_posting=p2,
            total_score=60.0)
        resp = self.client.get(
            f'/api/matching/results/?job_posting_id={self.posting.id}')
        self.assertEqual(resp.json()['count'], 1)


@override_settings(RBAC_STRICT=False)
class TestProvidersView(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user('match_test5', password='pass')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.client.credentials(
            HTTP_X_COMPANY_ID=COMPANY_STR,
            HTTP_X_USER_ROLE='internal_hr',
        )

    def test_providers_lists_rule_based(self):
        resp = self.client.get('/api/matching/providers/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('rule_based', resp.json()['available'])

    def test_active_provider_is_rule_based(self):
        resp = self.client.get('/api/matching/providers/')
        self.assertEqual(resp.json()['active'], 'rule_based')
