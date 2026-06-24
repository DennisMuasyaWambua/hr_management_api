import logging

from django.utils import timezone

from .models import JobMatchScore
from .providers.base import ProviderRegistry

logger = logging.getLogger(__name__)


class MatchingEngine:

    @classmethod
    def score(cls, candidate, job_posting) -> JobMatchScore:
        provider = ProviderRegistry.get_active()
        result = provider.score(candidate, job_posting)

        score, created = JobMatchScore.objects.update_or_create(
            candidate=candidate,
            job_posting=job_posting,
            defaults={
                'company_id': candidate.company_id,
                'provider': provider.name,
                'skill_score': result.skill_score,
                'experience_score': result.experience_score,
                'education_score': result.education_score,
                'location_score': result.location_score,
                'total_score': result.total_score,
                'scoring_notes': result.notes,
            },
        )

        cls._update_breakdown(candidate, result)
        cls._update_candidate_ai_score(candidate, result)

        logger.debug(
            'Scored candidate %s vs job %s → %.2f (%s)',
            candidate.id, job_posting.id, result.total_score, provider.name,
        )
        return score

    @classmethod
    def score_bulk(cls, job_posting, candidates) -> list[JobMatchScore]:
        return [cls.score(c, job_posting) for c in candidates]

    @classmethod
    def rank(cls, job_posting, company_id) -> list[JobMatchScore]:
        return list(
            JobMatchScore.objects.filter(
                job_posting=job_posting, company_id=company_id,
            ).select_related('candidate').order_by('-total_score')
        )

    @staticmethod
    def _update_breakdown(candidate, result):
        from apps.recruitment.models import CandidateScoreBreakdown
        CandidateScoreBreakdown.objects.update_or_create(
            candidate=candidate,
            defaults={
                'company_id': candidate.company_id,
                'skill_score': result.skill_score,
                'experience_score': result.experience_score,
                'location_score': result.location_score,
                'total_score': result.total_score,
                'scoring_notes': result.notes,
                'scored_at': timezone.now(),
            },
        )

    @staticmethod
    def _update_candidate_ai_score(candidate, result):
        candidate.ai_score = result.total_score
        candidate.save(update_fields=['ai_score'])
