import uuid

from django.contrib.auth.models import User
from django.test import override_settings
from rest_framework.test import APIClient, APITestCase

from apps.recruitment.models import (
    Candidate, CandidateActivity, CandidateNote,
    CandidateTag, CandidateTagAssignment, JobPosting,
    Referral, TalentPool, TalentPoolMember,
)

COMPANY = uuid.UUID('00000000-0000-0000-0000-000000000050')
COMPANY_STR = str(COMPANY)
OTHER_COMPANY = uuid.UUID('00000000-0000-0000-0000-000000000051')


def _posting(company_id=None):
    return JobPosting.objects.create(
        company_id=company_id or COMPANY,
        title='Software Engineer',
        description='Build things.',
    )


def _candidate(posting=None, company_id=None, **kwargs):
    if posting is None:
        posting = _posting(company_id=company_id or COMPANY)
    defaults = dict(
        company_id=company_id or COMPANY,
        job_posting=posting,
        full_name='Alice Test',
        email='alice@example.com',
    )
    defaults.update(kwargs)
    return Candidate.objects.create(**defaults)


def _pool(company_id=None, **kwargs):
    defaults = dict(company_id=company_id or COMPANY, name='Senior Pool')
    defaults.update(kwargs)
    return TalentPool.objects.create(**defaults)


def _tag(company_id=None, name='Python', **kwargs):
    defaults = dict(company_id=company_id or COMPANY, name=name)
    defaults.update(kwargs)
    return CandidateTag.objects.create(**defaults)


@override_settings(RBAC_STRICT=False)
class TestTalentPoolViewSet(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user('crm_test1', password='pass')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.client.credentials(
            HTTP_X_COMPANY_ID=COMPANY_STR,
            HTTP_X_USER_ROLE='internal_hr',
            HTTP_X_USER_ID=str(uuid.uuid4()),
        )

    def test_list_empty(self):
        resp = self.client.get('/api/talent-pools/')
        self.assertEqual(resp.status_code, 200)

    def test_create_pool(self):
        resp = self.client.post('/api/talent-pools/', {'name': 'Passive Candidates'}, format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()['name'], 'Passive Candidates')
        self.assertEqual(resp.json()['company_id'], COMPANY_STR)

    def test_list_scoped_to_company(self):
        _pool()
        _pool(company_id=OTHER_COMPANY, name='Other Pool')
        resp = self.client.get('/api/talent-pools/')
        results = resp.json()['results']
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['name'], 'Senior Pool')

    def test_retrieve_pool(self):
        pool = _pool()
        resp = self.client.get(f'/api/talent-pools/{pool.id}/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['id'], str(pool.id))

    def test_retrieve_other_company_404(self):
        pool = _pool(company_id=OTHER_COMPANY)
        resp = self.client.get(f'/api/talent-pools/{pool.id}/')
        self.assertEqual(resp.status_code, 404)

    def test_update_pool(self):
        pool = _pool()
        resp = self.client.patch(f'/api/talent-pools/{pool.id}/',
                                 {'name': 'Updated Pool'}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['name'], 'Updated Pool')

    def test_delete_pool(self):
        pool = _pool()
        resp = self.client.delete(f'/api/talent-pools/{pool.id}/')
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(TalentPool.objects.filter(pk=pool.id).exists())

    def test_add_candidate(self):
        pool = _pool()
        candidate = _candidate()
        resp = self.client.post(
            f'/api/talent-pools/{pool.id}/add-candidate/',
            {'candidate_id': str(candidate.id)},
            format='json',
        )
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(TalentPoolMember.objects.filter(pool=pool, candidate=candidate).exists())

    def test_add_candidate_creates_activity(self):
        pool = _pool()
        candidate = _candidate()
        self.client.post(
            f'/api/talent-pools/{pool.id}/add-candidate/',
            {'candidate_id': str(candidate.id)},
            format='json',
        )
        self.assertTrue(CandidateActivity.objects.filter(
            candidate=candidate, event_type='pool_added').exists())

    def test_add_candidate_duplicate_returns_409(self):
        pool = _pool()
        candidate = _candidate()
        TalentPoolMember.objects.create(pool=pool, candidate=candidate)
        resp = self.client.post(
            f'/api/talent-pools/{pool.id}/add-candidate/',
            {'candidate_id': str(candidate.id)},
            format='json',
        )
        self.assertEqual(resp.status_code, 409)

    def test_add_candidate_missing_id_returns_400(self):
        pool = _pool()
        resp = self.client.post(f'/api/talent-pools/{pool.id}/add-candidate/', {}, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_remove_candidate(self):
        pool = _pool()
        candidate = _candidate()
        TalentPoolMember.objects.create(pool=pool, candidate=candidate)
        resp = self.client.post(
            f'/api/talent-pools/{pool.id}/remove-candidate/',
            {'candidate_id': str(candidate.id)},
            format='json',
        )
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(TalentPoolMember.objects.filter(pool=pool, candidate=candidate).exists())

    def test_remove_candidate_not_in_pool_returns_404(self):
        pool = _pool()
        candidate = _candidate()
        resp = self.client.post(
            f'/api/talent-pools/{pool.id}/remove-candidate/',
            {'candidate_id': str(candidate.id)},
            format='json',
        )
        self.assertEqual(resp.status_code, 404)

    def test_members_endpoint(self):
        pool = _pool()
        candidate = _candidate()
        TalentPoolMember.objects.create(pool=pool, candidate=candidate)
        resp = self.client.get(f'/api/talent-pools/{pool.id}/members/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['count'], 1)
        self.assertEqual(resp.json()['results'][0]['candidate_name'], 'Alice Test')

    def test_member_count_in_list(self):
        pool = _pool()
        candidate = _candidate()
        TalentPoolMember.objects.create(pool=pool, candidate=candidate)
        resp = self.client.get('/api/talent-pools/')
        self.assertEqual(resp.json()['results'][0]['member_count'], 1)


@override_settings(RBAC_STRICT=False)
class TestCandidateTagViewSet(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user('crm_test2', password='pass')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.client.credentials(
            HTTP_X_COMPANY_ID=COMPANY_STR,
            HTTP_X_USER_ROLE='internal_hr',
        )

    def test_create_tag(self):
        resp = self.client.post('/api/candidate-tags/',
                                {'name': 'Python', 'color': '#3B82F6'}, format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()['name'], 'Python')

    def test_list_tags_scoped(self):
        _tag()
        _tag(company_id=OTHER_COMPANY, name='Other Tag')
        resp = self.client.get('/api/candidate-tags/')
        self.assertEqual(len(resp.json()['results']), 1)

    def test_delete_tag(self):
        tag = _tag()
        resp = self.client.delete(f'/api/candidate-tags/{tag.id}/')
        self.assertEqual(resp.status_code, 204)

    def test_update_tag_color(self):
        tag = _tag()
        resp = self.client.patch(f'/api/candidate-tags/{tag.id}/',
                                 {'color': '#EF4444'}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['color'], '#EF4444')


@override_settings(RBAC_STRICT=False)
class TestCandidateTagAssignmentViewSet(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user('crm_test3', password='pass')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.client.credentials(
            HTTP_X_COMPANY_ID=COMPANY_STR,
            HTTP_X_USER_ROLE='internal_hr',
        )
        self.candidate = _candidate()
        self.tag = _tag()

    def test_assign_tag(self):
        resp = self.client.post(
            '/api/candidate-tag-assignments/',
            {'tag': str(self.tag.id), 'candidate': str(self.candidate.id)},
            format='json',
        )
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(CandidateTagAssignment.objects.filter(
            tag=self.tag, candidate=self.candidate).exists())

    def test_assign_tag_creates_activity(self):
        self.client.post(
            '/api/candidate-tag-assignments/',
            {'tag': str(self.tag.id), 'candidate': str(self.candidate.id)},
            format='json',
        )
        self.assertTrue(CandidateActivity.objects.filter(
            candidate=self.candidate, event_type='tag_added').exists())

    def test_delete_assignment_creates_tag_removed_activity(self):
        assignment = CandidateTagAssignment.objects.create(
            tag=self.tag, candidate=self.candidate)
        self.client.delete(f'/api/candidate-tag-assignments/{assignment.id}/')
        self.assertTrue(CandidateActivity.objects.filter(
            candidate=self.candidate, event_type='tag_removed').exists())

    def test_filter_by_candidate(self):
        other_candidate = _candidate(email='bob@example.com', full_name='Bob')
        CandidateTagAssignment.objects.create(tag=self.tag, candidate=self.candidate)
        tag2 = _tag(name='Java')
        CandidateTagAssignment.objects.create(tag=tag2, candidate=other_candidate)
        resp = self.client.get(
            f'/api/candidate-tag-assignments/?candidate_id={self.candidate.id}')
        self.assertEqual(len(resp.json()['results']), 1)


@override_settings(RBAC_STRICT=False)
class TestCandidateNoteViewSet(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user('crm_test4', password='pass')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.client.credentials(
            HTTP_X_COMPANY_ID=COMPANY_STR,
            HTTP_X_USER_ROLE='internal_hr',
        )
        self.candidate = _candidate()

    def test_create_note(self):
        resp = self.client.post('/api/candidate-notes/', {
            'candidate': str(self.candidate.id),
            'note_type': 'call',
            'body': 'Had a great call today.',
        }, format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()['note_type'], 'call')
        self.assertEqual(resp.json()['company_id'], COMPANY_STR)

    def test_create_note_creates_activity(self):
        self.client.post('/api/candidate-notes/', {
            'candidate': str(self.candidate.id),
            'note_type': 'email',
            'body': 'Sent follow-up email.',
        }, format='json')
        self.assertTrue(CandidateActivity.objects.filter(
            candidate=self.candidate, event_type='note_added').exists())

    def test_list_notes_scoped_by_candidate(self):
        other_candidate = _candidate(email='carol@example.com', full_name='Carol')
        CandidateNote.objects.create(
            company_id=COMPANY, candidate=self.candidate, note_type='note', body='Note 1')
        CandidateNote.objects.create(
            company_id=COMPANY, candidate=other_candidate, note_type='note', body='Note 2')
        resp = self.client.get(
            f'/api/candidate-notes/?candidate_id={self.candidate.id}')
        self.assertEqual(len(resp.json()['results']), 1)

    def test_update_note(self):
        note = CandidateNote.objects.create(
            company_id=COMPANY, candidate=self.candidate, note_type='note', body='Original')
        resp = self.client.patch(f'/api/candidate-notes/{note.id}/',
                                 {'body': 'Updated'}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['body'], 'Updated')

    def test_delete_note(self):
        note = CandidateNote.objects.create(
            company_id=COMPANY, candidate=self.candidate, note_type='note', body='To delete')
        resp = self.client.delete(f'/api/candidate-notes/{note.id}/')
        self.assertEqual(resp.status_code, 204)


@override_settings(RBAC_STRICT=False)
class TestCandidateActivityViewSet(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user('crm_test5', password='pass')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.client.credentials(
            HTTP_X_COMPANY_ID=COMPANY_STR,
            HTTP_X_USER_ROLE='internal_hr',
        )
        self.candidate = _candidate()

    def test_list_activities(self):
        CandidateActivity.objects.create(
            company_id=COMPANY, candidate=self.candidate,
            event_type='applied', description='Applied via careers site')
        resp = self.client.get(
            f'/api/candidate-activities/?candidate_id={self.candidate.id}')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()['results']), 1)

    def test_activities_scoped_to_company(self):
        other_candidate = _candidate(company_id=OTHER_COMPANY, email='x@x.com',
                                     full_name='X', posting=None)
        CandidateActivity.objects.create(
            company_id=COMPANY, candidate=self.candidate, event_type='applied', description='')
        CandidateActivity.objects.create(
            company_id=OTHER_COMPANY, candidate=other_candidate, event_type='applied', description='')
        resp = self.client.get('/api/candidate-activities/')
        for act in resp.json()['results']:
            self.assertEqual(act['company_id'], COMPANY_STR)

    def test_post_not_allowed(self):
        resp = self.client.post('/api/candidate-activities/', {}, format='json')
        self.assertEqual(resp.status_code, 405)


@override_settings(RBAC_STRICT=False)
class TestReferralViewSet(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user('crm_test6', password='pass')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.client.credentials(
            HTTP_X_COMPANY_ID=COMPANY_STR,
            HTTP_X_USER_ROLE='internal_hr',
        )
        self.candidate = _candidate()

    def test_create_referral(self):
        resp = self.client.post('/api/referrals/', {
            'candidate': str(self.candidate.id),
            'referrer_name': 'Bob Smith',
            'referrer_email': 'bob@acme.com',
        }, format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()['referrer_name'], 'Bob Smith')
        self.assertEqual(resp.json()['status'], 'pending')

    def test_create_referral_creates_activity(self):
        self.client.post('/api/referrals/', {
            'candidate': str(self.candidate.id),
            'referrer_name': 'Carol',
            'referrer_email': 'carol@acme.com',
        }, format='json')
        self.assertTrue(CandidateActivity.objects.filter(
            candidate=self.candidate, event_type='referral_submitted').exists())

    def test_list_referrals_scoped(self):
        Referral.objects.create(
            company_id=COMPANY, candidate=self.candidate,
            referrer_name='A', referrer_email='a@a.com')
        other = _candidate(company_id=OTHER_COMPANY, email='o@o.com',
                           full_name='Other', posting=None)
        Referral.objects.create(
            company_id=OTHER_COMPANY, candidate=other,
            referrer_name='B', referrer_email='b@b.com')
        resp = self.client.get('/api/referrals/')
        self.assertEqual(len(resp.json()['results']), 1)

    def test_filter_by_status(self):
        Referral.objects.create(
            company_id=COMPANY, candidate=self.candidate,
            referrer_name='A', referrer_email='a@a.com', status='pending')
        Referral.objects.create(
            company_id=COMPANY, candidate=self.candidate,
            referrer_name='B', referrer_email='b@b.com', status='hired')
        resp = self.client.get('/api/referrals/?status=pending')
        self.assertEqual(len(resp.json()['results']), 1)
        self.assertEqual(resp.json()['results'][0]['status'], 'pending')

    def test_update_referral_status(self):
        referral = Referral.objects.create(
            company_id=COMPANY, candidate=self.candidate,
            referrer_name='D', referrer_email='d@d.com', status='pending')
        resp = self.client.patch(f'/api/referrals/{referral.id}/',
                                 {'status': 'hired'}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['status'], 'hired')


@override_settings(RBAC_STRICT=False)
class TestCandidateSearchView(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user('crm_test7', password='pass')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.client.credentials(
            HTTP_X_COMPANY_ID=COMPANY_STR,
            HTTP_X_USER_ROLE='internal_hr',
        )
        self.posting = _posting()
        self.c1 = _candidate(
            posting=self.posting, full_name='Alice Dev',
            email='alice@dev.com', skills=['Python', 'Django'],
            location='Nairobi', experience_years=5,
            education_level='bachelors', is_passive=False,
        )
        self.c2 = _candidate(
            posting=self.posting, full_name='Bob Passive',
            email='bob@passive.com', skills=['React', 'TypeScript'],
            location='Mombasa', experience_years=2,
            education_level='masters', is_passive=True,
        )

    def test_search_no_filters_returns_all_company(self):
        resp = self.client.get('/api/candidate-search/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['count'], 2)

    def test_search_by_name(self):
        resp = self.client.get('/api/candidate-search/?q=alice')
        self.assertEqual(resp.json()['count'], 1)
        self.assertEqual(resp.json()['results'][0]['full_name'], 'Alice Dev')

    def test_search_by_location(self):
        resp = self.client.get('/api/candidate-search/?location=Nairobi')
        self.assertEqual(resp.json()['count'], 1)

    def test_search_is_passive_true(self):
        resp = self.client.get('/api/candidate-search/?is_passive=true')
        self.assertEqual(resp.json()['count'], 1)
        self.assertEqual(resp.json()['results'][0]['full_name'], 'Bob Passive')

    def test_search_is_passive_false(self):
        resp = self.client.get('/api/candidate-search/?is_passive=false')
        self.assertEqual(resp.json()['count'], 1)
        self.assertEqual(resp.json()['results'][0]['full_name'], 'Alice Dev')

    def test_search_experience_min(self):
        resp = self.client.get('/api/candidate-search/?experience_min=4')
        self.assertEqual(resp.json()['count'], 1)

    def test_search_experience_max(self):
        resp = self.client.get('/api/candidate-search/?experience_max=3')
        self.assertEqual(resp.json()['count'], 1)

    def test_search_education_level(self):
        resp = self.client.get('/api/candidate-search/?education_level=masters')
        self.assertEqual(resp.json()['count'], 1)
        self.assertEqual(resp.json()['results'][0]['full_name'], 'Bob Passive')

    def test_search_by_pool(self):
        pool = _pool()
        TalentPoolMember.objects.create(pool=pool, candidate=self.c1)
        resp = self.client.get(f'/api/candidate-search/?pool_id={pool.id}')
        self.assertEqual(resp.json()['count'], 1)
        self.assertEqual(resp.json()['results'][0]['full_name'], 'Alice Dev')

    def test_search_by_tag(self):
        tag = _tag(name='Senior')
        CandidateTagAssignment.objects.create(tag=tag, candidate=self.c1)
        resp = self.client.get(f'/api/candidate-search/?tag_ids={tag.id}')
        self.assertEqual(resp.json()['count'], 1)

    def test_search_no_company_header_returns_400(self):
        client = APIClient()
        client.force_authenticate(user=self.user)
        client.credentials(HTTP_X_USER_ROLE='internal_hr')
        resp = client.get('/api/candidate-search/')
        self.assertEqual(resp.status_code, 400)

    def test_search_pagination(self):
        resp = self.client.get('/api/candidate-search/?page=1&page_size=1')
        self.assertEqual(resp.json()['count'], 2)
        self.assertEqual(len(resp.json()['results']), 1)

    def test_search_other_company_excluded(self):
        other_posting = _posting(company_id=OTHER_COMPANY)
        _candidate(posting=other_posting, company_id=OTHER_COMPANY,
                   email='intruder@x.com', full_name='Intruder')
        resp = self.client.get('/api/candidate-search/')
        self.assertEqual(resp.json()['count'], 2)
