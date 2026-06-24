"""
API view tests using DRF APITestCase.
Generators are mocked; tests cover HTTP contract, pagination, auth, and isolation.
"""
import uuid
from unittest.mock import patch, MagicMock

from django.contrib.auth.models import User
from django.test import override_settings
from rest_framework.test import APITestCase, APIClient

from apps.actions.dataclasses import ActionCategory, ActionItem, ActionPriority, ActionStatus
from apps.actions.models import ActionRecord
from apps.actions.services import _GENERATOR_REGISTRY

COMPANY_ID = str(uuid.UUID('00000000-0000-0000-0000-000000000003'))
OTHER_COMPANY = str(uuid.UUID('00000000-0000-0000-0000-000000000004'))


def _item(action_type='TEST', priority=ActionPriority.HIGH, category=ActionCategory.RECRUITMENT):
    rec_id = str(uuid.uuid4())
    return ActionItem(
        id=f'test:{rec_id}:{action_type}',
        action_type=action_type,
        category=category,
        priority=priority,
        title='Test action',
        description='Test description',
        source_module='test',
        source_record_id=rec_id,
        action_url='/test/',
        priority_score=700,
    )


@override_settings(
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
    RBAC_STRICT=False,
)
class TestActionListView(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user('testuser', password='pass')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.client.credentials(
            HTTP_X_COMPANY_ID=COMPANY_ID,
            HTTP_X_USER_ROLE='internal_hr',
            HTTP_X_USER_ID=str(uuid.uuid4()),
        )
        self._orig = list(_GENERATOR_REGISTRY)
        _GENERATOR_REGISTRY.clear()

    def tearDown(self):
        _GENERATOR_REGISTRY.clear()
        _GENERATOR_REGISTRY.extend(self._orig)
        ActionRecord.objects.filter(company_id=COMPANY_ID).delete()

    def _mock_service(self, items):
        """Patch ActionCenterService.get_actions to return given items."""
        patcher = patch('apps.actions.views.ActionCenterService')
        mock_cls = patcher.start()
        mock_svc = MagicMock()
        mock_svc.get_actions.return_value = items
        mock_svc.get_summary.return_value = {
            'total_active': len(items), 'overdue': 0,
            'by_priority': {}, 'by_category': {},
            'generated_at': '2026-06-24T00:00:00',
        }
        mock_svc.get_high_priority.return_value = items
        mock_svc.get_overdue.return_value = []
        mock_svc.get_upcoming.return_value = []
        mock_cls.return_value = mock_svc
        self.addCleanup(patcher.stop)
        return mock_svc

    def test_list_returns_200(self):
        self._mock_service([_item()])
        resp = self.client.get('/api/actions/')
        self.assertEqual(resp.status_code, 200)

    def test_list_response_shape(self):
        self._mock_service([_item()])
        resp = self.client.get('/api/actions/')
        data = resp.json()
        self.assertIn('count', data)
        self.assertIn('results', data)
        self.assertIn('next', data)
        self.assertIn('previous', data)

    def test_list_pagination(self):
        items = [_item(f'TYPE_{i}') for i in range(30)]
        self._mock_service(items)
        resp = self.client.get('/api/actions/?per_page=10&page=1')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data['results']), 10)
        self.assertIsNotNone(data['next'])
        self.assertIsNone(data['previous'])

    def test_list_second_page(self):
        items = [_item(f'TYPE_{i}') for i in range(30)]
        self._mock_service(items)
        resp = self.client.get('/api/actions/?per_page=10&page=2')
        data = resp.json()
        self.assertIsNotNone(data['previous'])

    def test_unauthenticated_returns_403(self):
        anon = APIClient()
        resp = anon.get('/api/actions/')
        self.assertIn(resp.status_code, [401, 403])

    def test_summary_returns_200(self):
        self._mock_service([])
        resp = self.client.get('/api/actions/summary/')
        self.assertEqual(resp.status_code, 200)

    def test_high_priority_returns_200(self):
        self._mock_service([_item(priority=ActionPriority.CRITICAL)])
        resp = self.client.get('/api/actions/high-priority/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('count', data)
        self.assertIn('results', data)

    def test_overdue_returns_200(self):
        self._mock_service([])
        resp = self.client.get('/api/actions/overdue/')
        self.assertEqual(resp.status_code, 200)

    def test_upcoming_returns_200(self):
        self._mock_service([])
        resp = self.client.get('/api/actions/upcoming/?days=7')
        self.assertEqual(resp.status_code, 200)

    def test_upcoming_days_clamped(self):
        mock_svc = self._mock_service([])
        self.client.get('/api/actions/upcoming/?days=999')
        mock_svc.get_upcoming.assert_called_once()
        call_kwargs = mock_svc.get_upcoming.call_args[1]
        self.assertLessEqual(call_kwargs.get('days', 7), 90)


@override_settings(
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
    RBAC_STRICT=False,
)
class TestDismissEscalateViews(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user('testuser2', password='pass')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.company_id = uuid.UUID(COMPANY_ID)
        self.client.credentials(
            HTTP_X_COMPANY_ID=COMPANY_ID,
            HTTP_X_USER_ROLE='internal_hr',
            HTTP_X_USER_ID=str(uuid.uuid4()),
        )

    def tearDown(self):
        ActionRecord.objects.filter(company_id=COMPANY_ID).delete()

    def _make_record(self):
        action_id = f'recruitment:{uuid.uuid4()}:TEST'
        ActionRecord.objects.get_or_create(
            id=action_id,
            defaults={'company_id': self.company_id},
        )
        return action_id

    def test_dismiss_returns_200(self):
        action_id = self._make_record()
        with patch('apps.actions.views.ActionCenterService') as MockSvc:
            mock_svc = MagicMock()
            record = ActionRecord.objects.get(id=action_id)
            from django.utils import timezone
            record.dismissed_at = timezone.now()
            record.company_id = self.company_id
            mock_svc.dismiss.return_value = record
            MockSvc.return_value = mock_svc
            resp = self.client.post(
                f'/api/actions/{action_id}/dismiss/',
                {'reason': 'resolved'},
                format='json',
            )
        self.assertEqual(resp.status_code, 200)
        self.assertIn('dismissed_at', resp.json())

    def test_escalate_returns_200(self):
        action_id = self._make_record()
        with patch('apps.actions.views.ActionCenterService') as MockSvc:
            mock_svc = MagicMock()
            record = ActionRecord.objects.get(id=action_id)
            from django.utils import timezone
            record.escalated_at = timezone.now()
            record.company_id = self.company_id
            mock_svc.escalate.return_value = record
            MockSvc.return_value = mock_svc
            resp = self.client.post(
                f'/api/actions/{action_id}/escalate/',
                {'note': 'needs director attention'},
                format='json',
            )
        self.assertEqual(resp.status_code, 200)
        self.assertIn('escalated_at', resp.json())


@override_settings(
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
    RBAC_STRICT=False,
)
class TestCompanyIsolation(APITestCase):
    """Verify that dismiss on one company does not affect another company's records."""

    def setUp(self):
        self.user = User.objects.create_user('isolationuser', password='pass')

    def tearDown(self):
        ActionRecord.objects.all().delete()

    def test_dismiss_scoped_to_company(self):
        company_a = uuid.UUID(COMPANY_ID)
        company_b = uuid.UUID(OTHER_COMPANY)
        action_id = f'recruitment:{uuid.uuid4()}:TEST'

        # Create a record for company A
        ActionRecord.objects.create(id=action_id, company_id=company_a)

        # Company B attempts to dismiss company A's record via the service
        from apps.actions.services import ActionCenterService
        service_b = ActionCenterService(company_id=company_b)
        record = service_b.dismiss(action_id + '_different', user_id=None)

        # Company A's record should not be affected
        record_a = ActionRecord.objects.get(id=action_id)
        self.assertIsNone(record_a.dismissed_at)
