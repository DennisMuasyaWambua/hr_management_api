import uuid
from datetime import date

from django.contrib.auth.models import User
from django.test import override_settings
from rest_framework.test import APIClient, APITestCase

from apps.crm.models import (
    ClientContact, ClientContract, ClientMeetingNote,
    ClientSLA, Placement, RecruitmentClient,
)
from apps.recruitment.models import Candidate, JobPosting

COMPANY = uuid.UUID('00000000-0000-0000-0000-000000000060')
COMPANY_STR = str(COMPANY)
OTHER = uuid.UUID('00000000-0000-0000-0000-000000000061')


def _client(company_id=None, **kwargs):
    defaults = dict(company_id=company_id or COMPANY, name='Acme Corp')
    defaults.update(kwargs)
    return RecruitmentClient.objects.create(**defaults)


def _contact(client=None, **kwargs):
    if client is None:
        client = _client()
    defaults = dict(company_id=client.company_id, client=client,
                    full_name='Jane Doe')
    defaults.update(kwargs)
    return ClientContact.objects.create(**defaults)


def _contract(client=None, **kwargs):
    if client is None:
        client = _client()
    defaults = dict(company_id=client.company_id, client=client,
                    title='MSA 2026', start_date=date(2026, 1, 1))
    defaults.update(kwargs)
    return ClientContract.objects.create(**defaults)


def _posting(company_id=None):
    return JobPosting.objects.create(
        company_id=company_id or COMPANY,
        title='Backend Engineer', description='...',
    )


def _candidate(company_id=None):
    posting = _posting(company_id=company_id or COMPANY)
    return Candidate.objects.create(
        company_id=company_id or COMPANY,
        job_posting=posting,
        full_name='Bob Candidate',
        email='bob@test.com',
    )


@override_settings(RBAC_STRICT=False)
class TestRecruitmentClientViewSet(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user('crm3_test1', password='pass')
        self.client_api = APIClient()
        self.client_api.force_authenticate(user=self.user)
        self.client_api.credentials(
            HTTP_X_COMPANY_ID=COMPANY_STR,
            HTTP_X_USER_ROLE='internal_hr',
            HTTP_X_USER_ID=str(uuid.uuid4()),
        )

    def test_list_empty(self):
        resp = self.client_api.get('/api/clients/')
        self.assertEqual(resp.status_code, 200)

    def test_create_client(self):
        resp = self.client_api.post('/api/clients/', {
            'name': 'Beta Inc', 'industry': 'Tech', 'status': 'prospect',
        }, format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()['name'], 'Beta Inc')
        self.assertEqual(resp.json()['company_id'], COMPANY_STR)

    def test_list_scoped_to_company(self):
        _client()
        _client(company_id=OTHER, name='Other Corp')
        resp = self.client_api.get('/api/clients/')
        self.assertEqual(len(resp.json()['results']), 1)

    def test_retrieve_client(self):
        c = _client()
        resp = self.client_api.get(f'/api/clients/{c.id}/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['name'], 'Acme Corp')

    def test_retrieve_other_company_404(self):
        c = _client(company_id=OTHER)
        resp = self.client_api.get(f'/api/clients/{c.id}/')
        self.assertEqual(resp.status_code, 404)

    def test_update_client(self):
        c = _client()
        resp = self.client_api.patch(f'/api/clients/{c.id}/',
                                     {'status': 'inactive'}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['status'], 'inactive')

    def test_soft_delete(self):
        c = _client()
        resp = self.client_api.delete(f'/api/clients/{c.id}/')
        self.assertEqual(resp.status_code, 204)
        c.refresh_from_db()
        self.assertTrue(c.is_deleted)
        # Soft-deleted client no longer appears in list
        resp = self.client_api.get('/api/clients/')
        self.assertEqual(len(resp.json()['results']), 0)

    def test_filter_by_status(self):
        _client(status='active')
        _client(name='Old Corp', status='churned')
        resp = self.client_api.get('/api/clients/?status=active')
        self.assertEqual(len(resp.json()['results']), 1)

    def test_search_by_name(self):
        _client(name='Zebra Ltd')
        _client(name='Alpha LLC')
        resp = self.client_api.get('/api/clients/?q=Zebra')
        self.assertEqual(len(resp.json()['results']), 1)

    def test_contacts_nested_action(self):
        c = _client()
        _contact(client=c, full_name='Alice')
        _contact(client=c, full_name='Bob')
        resp = self.client_api.get(f'/api/clients/{c.id}/contacts/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['count'], 2)

    def test_contracts_nested_action(self):
        c = _client()
        _contract(client=c)
        resp = self.client_api.get(f'/api/clients/{c.id}/contracts/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['count'], 1)

    def test_meeting_notes_nested_action(self):
        c = _client()
        ClientMeetingNote.objects.create(
            company_id=COMPANY, client=c, meeting_date=date(2026, 6, 1),
            summary='Intro call')
        resp = self.client_api.get(f'/api/clients/{c.id}/meeting-notes/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['count'], 1)

    def test_placements_nested_action(self):
        c = _client()
        cand = _candidate()
        Placement.objects.create(
            company_id=COMPANY, client=c, candidate=cand,
            job_title='Engineer', start_date=date(2026, 7, 1))
        resp = self.client_api.get(f'/api/clients/{c.id}/placements/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['count'], 1)


@override_settings(RBAC_STRICT=False)
class TestClientContactViewSet(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user('crm3_test2', password='pass')
        self.client_api = APIClient()
        self.client_api.force_authenticate(user=self.user)
        self.client_api.credentials(
            HTTP_X_COMPANY_ID=COMPANY_STR,
            HTTP_X_USER_ROLE='internal_hr',
        )
        self.rc = _client()

    def test_create_contact(self):
        resp = self.client_api.post('/api/client-contacts/', {
            'client': str(self.rc.id),
            'full_name': 'Jane Smith',
            'email': 'jane@acme.com',
            'is_hiring_manager': True,
        }, format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()['full_name'], 'Jane Smith')

    def test_list_contacts_scoped(self):
        _contact(client=self.rc)
        other_rc = _client(company_id=OTHER, name='Other')
        _contact(client=other_rc)
        resp = self.client_api.get('/api/client-contacts/')
        self.assertEqual(len(resp.json()['results']), 1)

    def test_filter_by_client(self):
        rc2 = _client(name='Beta')
        _contact(client=self.rc, full_name='A')
        _contact(client=rc2, full_name='B')
        resp = self.client_api.get(f'/api/client-contacts/?client_id={self.rc.id}')
        self.assertEqual(len(resp.json()['results']), 1)

    def test_filter_by_hiring_manager(self):
        _contact(client=self.rc, full_name='HM', is_hiring_manager=True)
        _contact(client=self.rc, full_name='Regular', is_hiring_manager=False)
        resp = self.client_api.get('/api/client-contacts/?is_hiring_manager=true')
        self.assertEqual(len(resp.json()['results']), 1)
        self.assertEqual(resp.json()['results'][0]['full_name'], 'HM')

    def test_update_contact(self):
        ct = _contact(client=self.rc)
        resp = self.client_api.patch(f'/api/client-contacts/{ct.id}/',
                                     {'job_title': 'VP Engineering'}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['job_title'], 'VP Engineering')

    def test_delete_contact(self):
        ct = _contact(client=self.rc)
        resp = self.client_api.delete(f'/api/client-contacts/{ct.id}/')
        self.assertEqual(resp.status_code, 204)


@override_settings(RBAC_STRICT=False)
class TestClientContractViewSet(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user('crm3_test3', password='pass')
        self.client_api = APIClient()
        self.client_api.force_authenticate(user=self.user)
        self.client_api.credentials(
            HTTP_X_COMPANY_ID=COMPANY_STR,
            HTTP_X_USER_ROLE='internal_hr',
        )
        self.rc = _client()

    def test_create_contract(self):
        resp = self.client_api.post('/api/client-contracts/', {
            'client': str(self.rc.id),
            'title': 'Retained 2026',
            'contract_type': 'retained',
            'start_date': '2026-01-01',
            'fee_percentage': '15.00',
        }, format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()['contract_type'], 'retained')

    def test_list_contracts_scoped(self):
        _contract(client=self.rc)
        other_rc = _client(company_id=OTHER, name='Other')
        _contract(client=other_rc)
        resp = self.client_api.get('/api/client-contracts/')
        self.assertEqual(len(resp.json()['results']), 1)

    def test_filter_by_client(self):
        rc2 = _client(name='Beta')
        _contract(client=self.rc, title='C1')
        _contract(client=rc2, title='C2')
        resp = self.client_api.get(f'/api/client-contracts/?client_id={self.rc.id}')
        self.assertEqual(len(resp.json()['results']), 1)

    def test_filter_by_status(self):
        _contract(client=self.rc, title='Active C', status='active')
        _contract(client=self.rc, title='Draft C', status='draft')
        resp = self.client_api.get('/api/client-contracts/?status=active')
        self.assertEqual(len(resp.json()['results']), 1)

    def test_slas_nested_includes_in_serializer(self):
        contract = _contract(client=self.rc)
        ClientSLA.objects.create(
            company_id=COMPANY, contract=contract,
            metric='Time to CV', target_days=3)
        resp = self.client_api.get(f'/api/client-contracts/{contract.id}/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()['slas']), 1)

    def test_slas_action(self):
        contract = _contract(client=self.rc)
        ClientSLA.objects.create(company_id=COMPANY, contract=contract,
                                  metric='Time to offer', target_days=7)
        resp = self.client_api.get(f'/api/client-contracts/{contract.id}/slas/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['count'], 1)


@override_settings(RBAC_STRICT=False)
class TestClientSLAViewSet(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user('crm3_test4', password='pass')
        self.client_api = APIClient()
        self.client_api.force_authenticate(user=self.user)
        self.client_api.credentials(
            HTTP_X_COMPANY_ID=COMPANY_STR,
            HTTP_X_USER_ROLE='internal_hr',
        )
        self.contract = _contract()

    def test_create_sla(self):
        resp = self.client_api.post('/api/client-slas/', {
            'contract': str(self.contract.id),
            'metric': 'First CV within',
            'target_days': 5,
        }, format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()['target_days'], 5)

    def test_delete_sla(self):
        sla = ClientSLA.objects.create(
            company_id=COMPANY, contract=self.contract,
            metric='SLA X', target_days=10)
        resp = self.client_api.delete(f'/api/client-slas/{sla.id}/')
        self.assertEqual(resp.status_code, 204)

    def test_filter_by_contract(self):
        c2 = _contract(title='Other contract')
        ClientSLA.objects.create(company_id=COMPANY, contract=self.contract,
                                  metric='SLA A', target_days=3)
        ClientSLA.objects.create(company_id=COMPANY, contract=c2,
                                  metric='SLA B', target_days=5)
        resp = self.client_api.get(f'/api/client-slas/?contract_id={self.contract.id}')
        self.assertEqual(len(resp.json()['results']), 1)


@override_settings(RBAC_STRICT=False)
class TestClientMeetingNoteViewSet(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user('crm3_test5', password='pass')
        self.client_api = APIClient()
        self.client_api.force_authenticate(user=self.user)
        self.client_api.credentials(
            HTTP_X_COMPANY_ID=COMPANY_STR,
            HTTP_X_USER_ROLE='internal_hr',
            HTTP_X_USER_ID=str(uuid.uuid4()),
        )
        self.rc = _client()

    def test_create_meeting_note(self):
        resp = self.client_api.post('/api/client-meeting-notes/', {
            'client': str(self.rc.id),
            'meeting_type': 'call',
            'meeting_date': '2026-06-24',
            'summary': 'Discussed retainer structure.',
            'attendees': ['Alice', 'Bob'],
            'action_items': ['Send proposal'],
        }, format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()['meeting_type'], 'call')
        self.assertEqual(resp.json()['attendees'], ['Alice', 'Bob'])

    def test_list_notes_scoped(self):
        ClientMeetingNote.objects.create(
            company_id=COMPANY, client=self.rc,
            meeting_date=date(2026, 6, 1), summary='Note 1')
        other_rc = _client(company_id=OTHER, name='Other')
        ClientMeetingNote.objects.create(
            company_id=OTHER, client=other_rc,
            meeting_date=date(2026, 6, 1), summary='Note 2')
        resp = self.client_api.get('/api/client-meeting-notes/')
        self.assertEqual(len(resp.json()['results']), 1)

    def test_filter_by_client(self):
        rc2 = _client(name='Beta')
        ClientMeetingNote.objects.create(
            company_id=COMPANY, client=self.rc,
            meeting_date=date(2026, 5, 1), summary='A')
        ClientMeetingNote.objects.create(
            company_id=COMPANY, client=rc2,
            meeting_date=date(2026, 5, 1), summary='B')
        resp = self.client_api.get(f'/api/client-meeting-notes/?client_id={self.rc.id}')
        self.assertEqual(len(resp.json()['results']), 1)

    def test_author_id_stamped(self):
        actor = str(uuid.uuid4())
        self.client_api.credentials(
            HTTP_X_COMPANY_ID=COMPANY_STR,
            HTTP_X_USER_ROLE='internal_hr',
            HTTP_X_USER_ID=actor,
        )
        resp = self.client_api.post('/api/client-meeting-notes/', {
            'client': str(self.rc.id),
            'meeting_date': '2026-06-24',
            'summary': 'Test',
        }, format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()['author_id'], actor)

    def test_update_note(self):
        note = ClientMeetingNote.objects.create(
            company_id=COMPANY, client=self.rc,
            meeting_date=date(2026, 6, 1), summary='Old summary')
        resp = self.client_api.patch(f'/api/client-meeting-notes/{note.id}/',
                                     {'summary': 'New summary'}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['summary'], 'New summary')


@override_settings(RBAC_STRICT=False)
class TestPlacementViewSet(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user('crm3_test6', password='pass')
        self.client_api = APIClient()
        self.client_api.force_authenticate(user=self.user)
        self.client_api.credentials(
            HTTP_X_COMPANY_ID=COMPANY_STR,
            HTTP_X_USER_ROLE='internal_hr',
        )
        self.rc = _client()
        self.candidate = _candidate()

    def test_create_placement(self):
        resp = self.client_api.post('/api/placements/', {
            'client': str(self.rc.id),
            'candidate': str(self.candidate.id),
            'job_title': 'Backend Engineer',
            'start_date': '2026-07-01',
            'salary': '120000.00',
        }, format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()['job_title'], 'Backend Engineer')
        self.assertEqual(resp.json()['status'], 'offered')

    def test_list_placements_scoped(self):
        Placement.objects.create(
            company_id=COMPANY, client=self.rc, candidate=self.candidate,
            job_title='Dev', start_date=date(2026, 7, 1))
        other_rc = _client(company_id=OTHER, name='Other')
        other_cand = _candidate(company_id=OTHER)
        Placement.objects.create(
            company_id=OTHER, client=other_rc, candidate=other_cand,
            job_title='Dev2', start_date=date(2026, 7, 1))
        resp = self.client_api.get('/api/placements/')
        self.assertEqual(len(resp.json()['results']), 1)

    def test_filter_by_client(self):
        rc2 = _client(name='Beta')
        cand2 = _candidate()
        Placement.objects.create(company_id=COMPANY, client=self.rc,
                                  candidate=self.candidate, job_title='A',
                                  start_date=date(2026, 7, 1))
        Placement.objects.create(company_id=COMPANY, client=rc2,
                                  candidate=cand2, job_title='B',
                                  start_date=date(2026, 7, 1))
        resp = self.client_api.get(f'/api/placements/?client_id={self.rc.id}')
        self.assertEqual(len(resp.json()['results']), 1)

    def test_filter_by_status(self):
        Placement.objects.create(company_id=COMPANY, client=self.rc,
                                  candidate=self.candidate, job_title='A',
                                  start_date=date(2026, 7, 1), status='accepted')
        cand2 = _candidate()
        Placement.objects.create(company_id=COMPANY, client=self.rc,
                                  candidate=cand2, job_title='B',
                                  start_date=date(2026, 7, 1), status='cancelled')
        resp = self.client_api.get('/api/placements/?status=accepted')
        self.assertEqual(len(resp.json()['results']), 1)

    def test_filter_by_candidate(self):
        cand2 = _candidate()
        Placement.objects.create(company_id=COMPANY, client=self.rc,
                                  candidate=self.candidate, job_title='A',
                                  start_date=date(2026, 7, 1))
        Placement.objects.create(company_id=COMPANY, client=self.rc,
                                  candidate=cand2, job_title='B',
                                  start_date=date(2026, 7, 1))
        resp = self.client_api.get(f'/api/placements/?candidate_id={self.candidate.id}')
        self.assertEqual(len(resp.json()['results']), 1)

    def test_update_placement_status(self):
        p = Placement.objects.create(
            company_id=COMPANY, client=self.rc, candidate=self.candidate,
            job_title='Dev', start_date=date(2026, 7, 1), status='offered')
        resp = self.client_api.patch(f'/api/placements/{p.id}/',
                                     {'status': 'started'}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['status'], 'started')

    def test_candidate_name_in_response(self):
        p = Placement.objects.create(
            company_id=COMPANY, client=self.rc, candidate=self.candidate,
            job_title='Dev', start_date=date(2026, 7, 1))
        resp = self.client_api.get(f'/api/placements/{p.id}/')
        self.assertEqual(resp.json()['candidate_name'], 'Bob Candidate')
