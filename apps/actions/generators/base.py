from __future__ import annotations

import abc
import logging
from typing import Optional
from uuid import UUID

from ..dataclasses import ActionItem

logger = logging.getLogger(__name__)


class BaseActionGenerator(abc.ABC):
    """
    Abstract base for all action generators.

    Contract:
      - generate() must return a list[ActionItem] using at most 4 DB queries.
      - No N+1 queries. Use select_related / prefetch_related / values() with IN lists.
      - employee_ids=None means the caller has company-wide visibility.
      - Never raise — let safe_generate() absorb failures gracefully.
    """
    category: str  # must be set as a class attribute on every subclass

    def __init__(self, company_id: UUID, employee_ids: Optional[list[UUID]] = None):
        self.company_id = company_id
        self.employee_ids = employee_ids

    @abc.abstractmethod
    def generate(self) -> list[ActionItem]:
        """Return ActionItems for this company. Max 4 DB queries."""
        ...  # pragma: no cover

    def safe_generate(self) -> list[ActionItem]:
        """Wraps generate() so a single broken generator never takes down the feed."""
        try:
            return self.generate()
        except Exception:
            logger.exception(
                '%s.generate() failed for company_id=%s',
                self.__class__.__name__,
                self.company_id,
            )
            return []

    @staticmethod
    def make_id(source_module: str, source_record_id: str, action_type: str) -> str:
        """Builds the deterministic ActionItem/ActionRecord PK."""
        return f'{source_module}:{source_record_id}:{action_type}'
