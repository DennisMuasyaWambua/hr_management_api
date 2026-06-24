"""
Service-layer tests. Generators are mocked so service logic is tested in isolation.
"""
import uuid
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from apps.actions.dataclasses import ActionCategory, ActionItem, ActionPriority, ActionStatus
from apps.actions.models import ActionRecord
from apps.actions.services import ActionCenterService, _GENERATOR_REGISTRY, _cache_key

COMPANY_ID = uuid.UUID('00000000-0000-0000-0000-000000000002')


def _item(action_type='FOO', priority=ActionPriority.HIGH, category=ActionCategory.RECRUITMENT,
          age_hours=1.0, due_date=None):
    rec_id = str(uuid.uuid4())
    return ActionItem(
        id=f'test:{rec_id}:{action_type}',
        action_type=action_type,
        category=category,
        priority=priority,
        title='Test item',
        description='Description',
        source_module='test',
        source_record_id=rec_id,
        action_url='/test/',
        age_hours=age_hours,
        due_date=due_date,
    )


@override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
class TestActionCenterService(TestCase):

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        # Clear the registry and inject a test generator
        self._original_registry = list(_GENERATOR_REGISTRY)
        _GENERATOR_REGISTRY.clear()

    def tearDown(self):
        _GENERATOR_REGISTRY.clear()
        _GENERATOR_REGISTRY.extend(self._original_registry)
        ActionRecord.objects.filter(company_id=COMPANY_ID).delete()

    def _register_items(self, items):
        class MockGenerator:
            def __init__(self, company_id, employee_ids=None):
                pass
            def safe_generate(self):
                return items
        _GENERATOR_REGISTRY.append(MockGenerator)

    def test_get_actions_returns_scored_items(self):
        self._register_items([_item('FOO'), _item('BAR')])
        service = ActionCenterService(company_id=COMPANY_ID)
        result = service.get_actions()
        self.assertEqual(len(result), 2)
        for item in result:
            self.assertGreater(item.priority_score, 0)

    def test_get_actions_sorted_by_priority_score_desc(self):
        low = _item('LOW', priority=ActionPriority.LOW)
        high = _item('HIGH', priority=ActionPriority.HIGH)
        self._register_items([low, high])
        service = ActionCenterService(company_id=COMPANY_ID)
        result = service.get_actions()
        self.assertGreaterEqual(result[0].priority_score, result[1].priority_score)

    def test_get_actions_filters_by_category(self):
        self._register_items([
            _item('A', category=ActionCategory.RECRUITMENT),
            _item('B', category=ActionCategory.LEAVE),
        ])
        service = ActionCenterService(company_id=COMPANY_ID)
        result = service.get_actions(category='recruitment')
        self.assertTrue(all(i.category.value == 'recruitment' for i in result))

    def test_get_actions_filters_by_status(self):
        self._register_items([_item('C')])
        service = ActionCenterService(company_id=COMPANY_ID)

        # Dismiss the item via service
        items = service.get_actions()
        self.assertEqual(len(items), 1)
        service.dismiss(items[0].id, user_id=None)

        # Force cache refresh so dismissed overlay is applied
        service.refresh()
        active = service.get_actions(status_filter='active')
        dismissed = service.get_actions(status_filter='dismissed')
        self.assertEqual(len(active), 0)
        self.assertEqual(len(dismissed), 1)

    def test_get_summary_structure(self):
        self._register_items([_item()])
        service = ActionCenterService(company_id=COMPANY_ID)
        summary = service.get_summary()
        self.assertIn('total_active', summary)
        self.assertIn('overdue', summary)
        self.assertIn('by_priority', summary)
        self.assertIn('by_category', summary)
        self.assertIn('generated_at', summary)

    def test_get_summary_counts_correctly(self):
        items = [
            _item(category=ActionCategory.RECRUITMENT),
            _item(category=ActionCategory.LEAVE),
        ]
        self._register_items(items)
        service = ActionCenterService(company_id=COMPANY_ID)
        summary = service.get_summary()
        self.assertEqual(summary['total_active'], 2)
        self.assertEqual(summary['by_category']['recruitment'], 1)
        self.assertEqual(summary['by_category']['leave'], 1)

    def test_dismiss_creates_action_record(self):
        self._register_items([_item('DISMISS_ME')])
        service = ActionCenterService(company_id=COMPANY_ID)
        items = service.get_actions()
        action_id = items[0].id

        record = service.dismiss(action_id, user_id=None, reason='not relevant')
        self.assertIsNotNone(record.dismissed_at)
        self.assertEqual(record.dismiss_reason, 'not relevant')
        db_record = ActionRecord.objects.get(id=action_id)
        self.assertIsNotNone(db_record.dismissed_at)

    def test_escalate_creates_action_record(self):
        self._register_items([_item('ESCALATE_ME')])
        service = ActionCenterService(company_id=COMPANY_ID)
        items = service.get_actions()
        action_id = items[0].id

        with patch.object(service, '_send_escalation_notification'):
            record = service.escalate(action_id, user_id=None, note='urgent')
        self.assertIsNotNone(record.escalated_at)
        self.assertEqual(record.escalate_note, 'urgent')

    def test_refresh_invalidates_cache(self):
        from django.core.cache import cache
        self._register_items([_item()])
        service = ActionCenterService(company_id=COMPANY_ID)
        service.get_actions()  # populates cache
        key = _cache_key(COMPANY_ID, 'generated')
        self.assertIsNotNone(cache.get(key))
        service.refresh()
        self.assertIsNone(cache.get(key))

    def test_company_isolation(self):
        other_company = uuid.UUID('00000000-0000-0000-0000-000000000099')
        self._register_items([_item()])

        service_a = ActionCenterService(company_id=COMPANY_ID)
        service_b = ActionCenterService(company_id=other_company)

        service_a.get_actions()  # populates cache for company A
        from django.core.cache import cache
        key_a = _cache_key(COMPANY_ID, 'generated')
        key_b = _cache_key(other_company, 'generated')
        self.assertIsNotNone(cache.get(key_a))
        self.assertIsNone(cache.get(key_b))


@override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
class TestCaching(TestCase):

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self._original_registry = list(_GENERATOR_REGISTRY)
        _GENERATOR_REGISTRY.clear()

    def tearDown(self):
        _GENERATOR_REGISTRY.clear()
        _GENERATOR_REGISTRY.extend(self._original_registry)

    def test_second_call_uses_cache(self):
        call_count = 0

        class CountingGenerator:
            def __init__(self, company_id, employee_ids=None):
                pass
            def safe_generate(self):
                nonlocal call_count
                call_count += 1
                return [_item()]

        _GENERATOR_REGISTRY.append(CountingGenerator)
        service = ActionCenterService(company_id=COMPANY_ID)
        service.get_actions()
        service.get_actions()
        self.assertEqual(call_count, 1)  # second call hits cache

    def test_refresh_forces_regenenration(self):
        call_count = 0

        class CountingGenerator:
            def __init__(self, company_id, employee_ids=None):
                pass
            def safe_generate(self):
                nonlocal call_count
                call_count += 1
                return [_item()]

        _GENERATOR_REGISTRY.append(CountingGenerator)
        service = ActionCenterService(company_id=COMPANY_ID)
        service.get_actions()
        service.refresh()
        service.get_actions()
        self.assertEqual(call_count, 2)
