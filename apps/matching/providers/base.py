from abc import ABC, abstractmethod
from typing import NamedTuple


class MatchResult(NamedTuple):
    skill_score: float
    experience_score: float
    education_score: float
    location_score: float
    total_score: float
    notes: str


class BaseMatchingProvider(ABC):
    name: str = ''

    @abstractmethod
    def score(self, candidate, job_posting) -> MatchResult:
        """Score a candidate against a job posting. Returns a MatchResult."""


class ProviderRegistry:
    _providers: dict = {}
    _active_name: str = 'rule_based'

    @classmethod
    def register(cls, provider: BaseMatchingProvider):
        cls._providers[provider.name] = provider

    @classmethod
    def get(cls, name: str) -> BaseMatchingProvider:
        provider = cls._providers.get(name)
        if provider is None:
            raise KeyError(f'No matching provider registered: {name!r}')
        return provider

    @classmethod
    def get_active(cls) -> BaseMatchingProvider:
        from django.conf import settings
        name = getattr(settings, 'MATCHING_PROVIDER', 'rule_based')
        return cls.get(name)

    @classmethod
    def list_providers(cls) -> list:
        return list(cls._providers.keys())
