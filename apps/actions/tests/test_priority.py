import datetime
import unittest

from apps.actions.dataclasses import ActionCategory, ActionItem, ActionPriority, ActionStatus
from apps.actions.priority import (
    AGE_BONUS_CEILING,
    BASE_SCORES,
    ESCALATION_RULES,
    URGENCY_MODIFIER,
    PriorityEngine,
)


def _make_item(priority=ActionPriority.HIGH, age_hours=0.0, due_date=None,
               category=ActionCategory.RECRUITMENT, action_type='INTERVIEW_OVERDUE'):
    return ActionItem(
        id=f'test:abc:{action_type}',
        action_type=action_type,
        category=category,
        priority=priority,
        title='Test',
        description='Test description',
        source_module='test',
        source_record_id='abc',
        action_url='/test/',
        age_hours=age_hours,
        due_date=due_date,
    )


class TestPriorityEngineScore(unittest.TestCase):

    def test_base_score_no_age_no_overdue(self):
        for priority in ActionPriority:
            score = PriorityEngine.score(priority, age_hours=0, is_overdue=False)
            self.assertEqual(score, BASE_SCORES[priority])

    def test_age_bonus_added(self):
        score = PriorityEngine.score(ActionPriority.HIGH, age_hours=10, is_overdue=False)
        self.assertEqual(score, BASE_SCORES[ActionPriority.HIGH] + 10)

    def test_age_bonus_capped(self):
        ceiling = AGE_BONUS_CEILING[ActionPriority.HIGH]
        score_at_ceiling = PriorityEngine.score(ActionPriority.HIGH, age_hours=ceiling)
        score_above_ceiling = PriorityEngine.score(ActionPriority.HIGH, age_hours=ceiling + 100)
        self.assertEqual(score_at_ceiling, score_above_ceiling)

    def test_urgency_added_when_overdue(self):
        base = PriorityEngine.score(ActionPriority.HIGH, age_hours=0, is_overdue=False)
        overdue = PriorityEngine.score(ActionPriority.HIGH, age_hours=0, is_overdue=True)
        self.assertEqual(overdue - base, URGENCY_MODIFIER[ActionPriority.HIGH])

    def test_compliance_multiplier(self):
        base = PriorityEngine.score(ActionPriority.HIGH, age_hours=0, is_compliance=False)
        with_mult = PriorityEngine.score(ActionPriority.HIGH, age_hours=0, is_compliance=True)
        self.assertGreater(with_mult, base)

    def test_score_capped_at_1000(self):
        score = PriorityEngine.score(
            ActionPriority.CRITICAL, age_hours=500, is_overdue=True, is_compliance=True,
        )
        self.assertLessEqual(score, 1000)

    def test_critical_scores_higher_than_high(self):
        critical = PriorityEngine.score(ActionPriority.CRITICAL, age_hours=0)
        high = PriorityEngine.score(ActionPriority.HIGH, age_hours=0)
        self.assertGreater(critical, high)

    def test_ordering_critical_gt_high_gt_medium_gt_low(self):
        scores = [PriorityEngine.score(p, age_hours=0) for p in [
            ActionPriority.CRITICAL, ActionPriority.HIGH,
            ActionPriority.MEDIUM, ActionPriority.LOW,
        ]]
        self.assertEqual(scores, sorted(scores, reverse=True))


class TestPriorityEngineEnrich(unittest.TestCase):

    def test_enrich_sets_priority_score(self):
        item = _make_item(priority=ActionPriority.MEDIUM, age_hours=5)
        result = PriorityEngine.enrich(item)
        self.assertGreater(result.priority_score, 0)
        self.assertIs(result, item)

    def test_enrich_adds_urgency_for_past_due(self):
        past = datetime.datetime.now(tz=datetime.timezone.utc) - datetime.timedelta(hours=1)
        overdue_item = _make_item(priority=ActionPriority.HIGH, due_date=past)
        future = datetime.datetime.now(tz=datetime.timezone.utc) + datetime.timedelta(hours=1)
        current_item = _make_item(priority=ActionPriority.HIGH, due_date=future)
        PriorityEngine.enrich(overdue_item)
        PriorityEngine.enrich(current_item)
        self.assertGreater(overdue_item.priority_score, current_item.priority_score)

    def test_compliance_category_gets_higher_score(self):
        recruit_item = _make_item(priority=ActionPriority.HIGH, category=ActionCategory.RECRUITMENT)
        compliance_item = _make_item(priority=ActionPriority.HIGH, category=ActionCategory.COMPLIANCE)
        PriorityEngine.enrich(recruit_item)
        PriorityEngine.enrich(compliance_item)
        self.assertGreater(compliance_item.priority_score, recruit_item.priority_score)


class TestSLADetection(unittest.TestCase):

    def test_known_action_type_returns_defined_hours(self):
        self.assertEqual(PriorityEngine.sla_hours('INTERVIEW_OVERDUE'), 72)
        self.assertEqual(PriorityEngine.sla_hours('LEAVE_PENDING_APPROVAL'), 24)

    def test_unknown_action_type_returns_default(self):
        self.assertEqual(PriorityEngine.sla_hours('UNKNOWN_TYPE'), 168)

    def test_sla_breached_when_age_exceeds_threshold(self):
        item = _make_item(action_type='INTERVIEW_OVERDUE', age_hours=73)
        self.assertTrue(PriorityEngine.is_sla_breached(item))

    def test_sla_not_breached_within_threshold(self):
        item = _make_item(action_type='INTERVIEW_OVERDUE', age_hours=10)
        self.assertFalse(PriorityEngine.is_sla_breached(item))
