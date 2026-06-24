import uuid

from django.contrib.auth.models import User
from django.test import override_settings
from rest_framework.test import APIClient, APITestCase

from apps.workflows.models import WorkflowDefinition, WorkflowExecution, WorkflowTask

COMPANY_ID = str(uuid.UUID('00000000-0000-0000-0000-000000000030'))
OTHER_COMPANY = str(uuid.UUID('00000000-0000-0000-0000-000000000031'))


def _make_definition(company_id=None, **kwargs):
    defaults = dict(
        company_id=uuid.UUID(company_id or COMPANY_ID),
        name='Test WF',
        trigger_type='candidate_applied',
        conditions=[],
        actions=[],
    )
    defaults.update(kwargs)
    return WorkflowDefinition.objects.create(**defaults)


@override_settings(RBAC_STRICT=False)
class TestWorkflowDefinitionViews(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user('wf_test_user', password='pass')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.client.credentials(
            HTTP_X_COMPANY_ID=COMPANY_ID,
            HTTP_X_USER_ROLE='internal_hr',
            HTTP_X_USER_ID=str(uuid.uuid4()),
        )

    def tearDown(self):
        WorkflowDefinition.objects.filter(company_id=COMPANY_ID).delete()

    def test_list_returns_200(self):
        resp = self.client.get('/api/workflows/')
        self.assertEqual(resp.status_code, 200)

    def test_list_empty(self):
        resp = self.client.get('/api/workflows/')
        self.assertEqual(resp.json()['count'], 0)

    def test_list_returns_own_company_only(self):
        _make_definition()
        _make_definition(company_id=OTHER_COMPANY, name='Other')
        resp = self.client.get('/api/workflows/')
        self.assertEqual(resp.json()['count'], 1)

    def test_create_returns_201(self):
        payload = {
            'name': 'Auto Welcome',
            'trigger_type': 'candidate_applied',
            'conditions': [],
            'actions': [{'type': 'create_task', 'params': {'title': 'Review'}}],
        }
        resp = self.client.post('/api/workflows/', payload, format='json')
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertEqual(data['name'], 'Auto Welcome')
        self.assertEqual(data['company_id'], COMPANY_ID)

    def test_create_sets_company_from_header(self):
        payload = {'name': 'WF', 'trigger_type': 'leave_submitted', 'conditions': [], 'actions': []}
        resp = self.client.post('/api/workflows/', payload, format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()['company_id'], COMPANY_ID)

    def test_retrieve_returns_200(self):
        wf = _make_definition()
        resp = self.client.get(f'/api/workflows/{wf.id}/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['id'], str(wf.id))

    def test_retrieve_other_company_returns_404(self):
        wf = _make_definition(company_id=OTHER_COMPANY)
        resp = self.client.get(f'/api/workflows/{wf.id}/')
        self.assertEqual(resp.status_code, 404)

    def test_patch_updates_name(self):
        wf = _make_definition()
        resp = self.client.patch(f'/api/workflows/{wf.id}/', {'name': 'Updated'}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['name'], 'Updated')

    def test_delete_returns_204(self):
        wf = _make_definition()
        resp = self.client.delete(f'/api/workflows/{wf.id}/')
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(WorkflowDefinition.objects.filter(id=wf.id).exists())

    def test_activate_sets_is_active_true(self):
        wf = _make_definition(is_active=False)
        resp = self.client.post(f'/api/workflows/{wf.id}/activate/')
        self.assertEqual(resp.status_code, 200)
        wf.refresh_from_db()
        self.assertTrue(wf.is_active)

    def test_deactivate_sets_is_active_false(self):
        wf = _make_definition(is_active=True)
        resp = self.client.post(f'/api/workflows/{wf.id}/deactivate/')
        self.assertEqual(resp.status_code, 200)
        wf.refresh_from_db()
        self.assertFalse(wf.is_active)

    def test_unauthenticated_returns_403(self):
        anon = APIClient()
        resp = anon.get('/api/workflows/')
        self.assertIn(resp.status_code, [401, 403])

    def test_filter_by_trigger_type(self):
        _make_definition(trigger_type='candidate_applied')
        _make_definition(name='Leave WF', trigger_type='leave_submitted')
        resp = self.client.get('/api/workflows/?trigger_type=leave_submitted')
        data = resp.json()
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['results'][0]['trigger_type'], 'leave_submitted')


@override_settings(RBAC_STRICT=False)
class TestWorkflowTemplateView(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user('tpl_user', password='pass')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.client.credentials(
            HTTP_X_COMPANY_ID=COMPANY_ID,
            HTTP_X_USER_ROLE='internal_hr',
            HTTP_X_USER_ID=str(uuid.uuid4()),
        )

    def test_templates_returns_200(self):
        resp = self.client.get('/api/workflows/templates/')
        self.assertEqual(resp.status_code, 200)

    def test_templates_returns_list(self):
        resp = self.client.get('/api/workflows/templates/')
        data = resp.json()
        self.assertIn('count', data)
        self.assertIn('results', data)
        self.assertGreater(data['count'], 0)

    def test_templates_have_required_fields(self):
        resp = self.client.get('/api/workflows/templates/')
        template = resp.json()['results'][0]
        self.assertIn('id', template)
        self.assertIn('name', template)
        self.assertIn('trigger_type', template)
        self.assertIn('actions', template)


@override_settings(RBAC_STRICT=False)
class TestWorkflowExecutionViews(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user('exec_user', password='pass')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.client.credentials(
            HTTP_X_COMPANY_ID=COMPANY_ID,
            HTTP_X_USER_ROLE='internal_hr',
            HTTP_X_USER_ID=str(uuid.uuid4()),
        )
        self.wf = _make_definition()

    def tearDown(self):
        WorkflowExecution.objects.filter(company_id=COMPANY_ID).delete()
        WorkflowDefinition.objects.filter(company_id=COMPANY_ID).delete()

    def _make_execution(self, **kwargs):
        defaults = dict(
            workflow=self.wf,
            trigger_type='candidate_applied',
            source_object_id=str(uuid.uuid4()),
            company_id=uuid.UUID(COMPANY_ID),
            status='completed',
        )
        defaults.update(kwargs)
        return WorkflowExecution.objects.create(**defaults)

    def test_execution_list_returns_200(self):
        resp = self.client.get('/api/workflows/executions/')
        self.assertEqual(resp.status_code, 200)

    def test_execution_list_returns_own_company(self):
        self._make_execution()
        resp = self.client.get('/api/workflows/executions/')
        self.assertEqual(resp.json()['count'], 1)

    def test_execution_detail_returns_200(self):
        ex = self._make_execution()
        resp = self.client.get(f'/api/workflows/executions/{ex.id}/')
        self.assertEqual(resp.status_code, 200)

    def test_execution_detail_includes_logs(self):
        ex = self._make_execution()
        resp = self.client.get(f'/api/workflows/executions/{ex.id}/')
        self.assertIn('logs', resp.json())

    def test_execution_detail_other_company_returns_404(self):
        ex = self._make_execution(company_id=uuid.UUID(OTHER_COMPANY))
        resp = self.client.get(f'/api/workflows/executions/{ex.id}/')
        self.assertEqual(resp.status_code, 404)

    def test_execution_filter_by_status(self):
        self._make_execution(status='completed')
        self._make_execution(status='failed')
        resp = self.client.get('/api/workflows/executions/?status=completed')
        self.assertEqual(resp.json()['count'], 1)


@override_settings(RBAC_STRICT=False)
class TestWorkflowTaskViews(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user('task_user', password='pass')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.client.credentials(
            HTTP_X_COMPANY_ID=COMPANY_ID,
            HTTP_X_USER_ROLE='internal_hr',
            HTTP_X_USER_ID=str(uuid.uuid4()),
        )

    def tearDown(self):
        WorkflowTask.objects.filter(company_id=COMPANY_ID).delete()

    def _make_task(self, **kwargs):
        defaults = dict(company_id=uuid.UUID(COMPANY_ID), title='Test Task')
        defaults.update(kwargs)
        return WorkflowTask.objects.create(**defaults)

    def test_task_list_returns_200(self):
        resp = self.client.get('/api/workflows/tasks/')
        self.assertEqual(resp.status_code, 200)

    def test_task_create_returns_201(self):
        payload = {'title': 'New Task', 'priority': 'high'}
        resp = self.client.post('/api/workflows/tasks/', payload, format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()['title'], 'New Task')
        self.assertEqual(resp.json()['company_id'], COMPANY_ID)

    def test_task_retrieve_returns_200(self):
        task = self._make_task()
        resp = self.client.get(f'/api/workflows/tasks/{task.id}/')
        self.assertEqual(resp.status_code, 200)

    def test_task_complete_sets_status(self):
        task = self._make_task()
        resp = self.client.post(f'/api/workflows/tasks/{task.id}/complete/')
        self.assertEqual(resp.status_code, 200)
        task.refresh_from_db()
        self.assertEqual(task.status, 'completed')
        self.assertIsNotNone(task.completed_at)

    def test_task_delete_returns_204(self):
        task = self._make_task()
        resp = self.client.delete(f'/api/workflows/tasks/{task.id}/')
        self.assertEqual(resp.status_code, 204)

    def test_task_filter_by_status(self):
        self._make_task(status='open')
        self._make_task(status='completed')
        resp = self.client.get('/api/workflows/tasks/?status=open')
        self.assertEqual(resp.json()['count'], 1)

    def test_task_other_company_not_visible(self):
        self._make_task(company_id=uuid.UUID(OTHER_COMPANY))
        resp = self.client.get('/api/workflows/tasks/')
        self.assertEqual(resp.json()['count'], 0)
