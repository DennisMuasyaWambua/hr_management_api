from __future__ import annotations

import datetime

from .dataclasses import ActionCategory, ActionItem, ActionPriority

# Base score per priority tier
BASE_SCORES: dict[ActionPriority, int] = {
    ActionPriority.CRITICAL: 1000,
    ActionPriority.HIGH: 700,
    ActionPriority.MEDIUM: 400,
    ActionPriority.LOW: 100,
}

# Age bonus: +1 per hour, capped per tier
AGE_BONUS_CEILING: dict[ActionPriority, int] = {
    ActionPriority.CRITICAL: 200,
    ActionPriority.HIGH: 150,
    ActionPriority.MEDIUM: 100,
    ActionPriority.LOW: 50,
}

# Additional score when action is past its due date
URGENCY_MODIFIER: dict[ActionPriority, int] = {
    ActionPriority.CRITICAL: 300,
    ActionPriority.HIGH: 200,
    ActionPriority.MEDIUM: 100,
    ActionPriority.LOW: 50,
}

# Compliance category gets a 1.5× multiplier for regulatory weight
COMPLIANCE_MULTIPLIER = 1.5

# SLA thresholds (hours) before escalation eligibility per action type
ESCALATION_RULES: dict[str, int] = {
    'INTERVIEW_OVERDUE': 72,
    'OFFER_AWAITING_RESPONSE': 120,
    'PIPELINE_STALLED': 336,
    'JOB_CLOSING_SOON': 24,
    'LEAVE_PENDING_APPROVAL': 24,
    'LEAVE_RECALL_PENDING': 24,
    'LOW_LEAVE_BALANCE': 720,
    'DOCUMENT_MISSING': 168,
    'DOCUMENT_AWAITING_VERIFICATION': 48,
    'BACKGROUND_CHECK_PENDING': 72,
    'BACKGROUND_CHECK_FLAGGED': 24,
    'CONTRACT_EXPIRING': 48,
    'PROBATION_REVIEW_DUE': 48,
    'STATUTORY_NUMBER_MISSING': 336,
    'PERFORMANCE_REVIEW_OVERDUE': 168,
    'GEOFENCE_VIOLATION_OPEN': 24,
    'EXIT_CLEARANCE_STALLED': 72,
    'EXIT_OVERDUE': 24,
    'FINAL_DUES_PENDING': 48,
    'COMPLIANCE_ALERT_OPEN': 48,
    'CERTIFICATE_EXPIRING': 48,
    'DISCIPLINARY_OPEN': 168,
}

_DEFAULT_SLA_HOURS = 168


class PriorityEngine:
    """
    Scores ActionItems: base_score + min(age_hours, ceiling) + urgency + compliance_multiplier.
    Final score is capped at 1000 to maintain a clear 0-1000 range.
    """

    @staticmethod
    def score(
        priority: ActionPriority,
        age_hours: float,
        is_overdue: bool = False,
        is_compliance: bool = False,
    ) -> int:
        base = BASE_SCORES[priority]
        age_bonus = min(int(age_hours), AGE_BONUS_CEILING[priority])
        urgency = URGENCY_MODIFIER[priority] if is_overdue else 0
        raw = base + age_bonus + urgency
        if is_compliance:
            raw = int(raw * COMPLIANCE_MULTIPLIER)
        return min(raw, 1000)

    @staticmethod
    def enrich(item: ActionItem) -> ActionItem:
        """Compute and set priority_score on an ActionItem in place. Returns item."""
        now = datetime.datetime.now(tz=datetime.timezone.utc)
        is_overdue = bool(item.due_date and item.due_date < now)
        is_compliance = item.category == ActionCategory.COMPLIANCE
        item.priority_score = PriorityEngine.score(
            item.priority, item.age_hours, is_overdue, is_compliance
        )
        return item

    @staticmethod
    def sla_hours(action_type: str) -> int:
        return ESCALATION_RULES.get(action_type, _DEFAULT_SLA_HOURS)

    @staticmethod
    def is_sla_breached(item: ActionItem) -> bool:
        return item.age_hours >= PriorityEngine.sla_hours(item.action_type)
