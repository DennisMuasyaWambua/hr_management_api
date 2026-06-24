from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class ActionPriority(str, Enum):
    CRITICAL = 'critical'
    HIGH = 'high'
    MEDIUM = 'medium'
    LOW = 'low'


class ActionCategory(str, Enum):
    RECRUITMENT = 'recruitment'
    LEAVE = 'leave'
    ONBOARDING = 'onboarding'
    EMPLOYEE_LIFECYCLE = 'employee_lifecycle'
    OFFBOARDING = 'offboarding'
    COMPLIANCE = 'compliance'


class ActionStatus(str, Enum):
    ACTIVE = 'active'
    DISMISSED = 'dismissed'
    ESCALATED = 'escalated'


@dataclass
class ActionItem:
    """
    Internal contract for a single action surfaced by a generator.
    Never persisted directly — source models are always authoritative.
    """
    id: str                           # "{source_module}:{source_record_id}:{action_type}"
    action_type: str                  # e.g. 'INTERVIEW_OVERDUE'
    category: ActionCategory
    priority: ActionPriority
    title: str
    description: str
    source_module: str
    source_record_id: str
    action_url: str
    priority_score: int = 0           # set by PriorityEngine.enrich()
    status: ActionStatus = ActionStatus.ACTIVE
    due_date: Optional[datetime] = None
    age_hours: float = 0.0
    employee_id: Optional[str] = None    # UUID string
    candidate_id: Optional[str] = None   # UUID string
    assigned_to: Optional[str] = None    # UUID string
    metadata: dict[str, Any] = field(default_factory=dict)
    first_seen_at: Optional[datetime] = None
    dismissed_at: Optional[datetime] = None
    escalated_at: Optional[datetime] = None
