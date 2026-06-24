from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import HasModulePermission, request_company_id
from apps.recruitment.models import Candidate, JobPosting

from .engine import MatchingEngine
from .models import JobMatchScore
from .providers.base import ProviderRegistry
from .serializers import JobMatchScoreSerializer, RankedCandidateSerializer


def _get_company(request):
    return request_company_id(request)


class ScoreView(APIView):
    permission_classes = [HasModulePermission]
    rbac_module = 'matching'

    def post(self, request):
        candidate_id = request.data.get('candidate_id')
        job_posting_id = request.data.get('job_posting_id')
        if not candidate_id or not job_posting_id:
            return Response(
                {'detail': 'candidate_id and job_posting_id are required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        company_id = _get_company(request)
        try:
            candidate = Candidate.objects.get(pk=candidate_id,
                                              company_id=company_id,
                                              is_deleted=False)
            job_posting = JobPosting.objects.get(pk=job_posting_id,
                                                 company_id=company_id,
                                                 is_deleted=False)
        except (Candidate.DoesNotExist, JobPosting.DoesNotExist) as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_404_NOT_FOUND)

        score = MatchingEngine.score(candidate, job_posting)
        return Response(JobMatchScoreSerializer(score).data, status=status.HTTP_200_OK)


class ScoreBulkView(APIView):
    permission_classes = [HasModulePermission]
    rbac_module = 'matching'

    def post(self, request):
        job_posting_id = request.data.get('job_posting_id')
        if not job_posting_id:
            return Response({'detail': 'job_posting_id required.'},
                            status=status.HTTP_400_BAD_REQUEST)
        company_id = _get_company(request)
        try:
            job_posting = JobPosting.objects.get(pk=job_posting_id,
                                                 company_id=company_id,
                                                 is_deleted=False)
        except JobPosting.DoesNotExist:
            return Response({'detail': 'Job posting not found.'},
                            status=status.HTTP_404_NOT_FOUND)

        candidate_ids = request.data.get('candidate_ids')
        if candidate_ids:
            candidates = list(Candidate.objects.filter(
                pk__in=candidate_ids, company_id=company_id, is_deleted=False))
        else:
            candidates = list(Candidate.objects.filter(
                job_posting=job_posting, company_id=company_id, is_deleted=False))

        scores = MatchingEngine.score_bulk(job_posting, candidates)
        return Response({
            'scored': len(scores),
            'results': JobMatchScoreSerializer(scores, many=True).data,
        }, status=status.HTTP_200_OK)


class RankView(APIView):
    permission_classes = [HasModulePermission]
    rbac_module = 'matching'

    def get(self, request, job_posting_id):
        company_id = _get_company(request)
        try:
            job_posting = JobPosting.objects.get(pk=job_posting_id,
                                                 company_id=company_id,
                                                 is_deleted=False)
        except JobPosting.DoesNotExist:
            return Response({'detail': 'Job posting not found.'},
                            status=status.HTTP_404_NOT_FOUND)

        ranked = MatchingEngine.rank(job_posting, company_id)
        return Response({
            'job_posting_id': str(job_posting_id),
            'job_posting_title': job_posting.title,
            'count': len(ranked),
            'results': RankedCandidateSerializer(ranked, many=True).data,
        })


class ResultsView(APIView):
    permission_classes = [HasModulePermission]
    rbac_module = 'matching'

    def get(self, request):
        company_id = _get_company(request)
        qs = JobMatchScore.objects.filter(company_id=company_id).select_related(
            'candidate', 'job_posting')

        candidate_id = request.query_params.get('candidate_id')
        if candidate_id:
            qs = qs.filter(candidate_id=candidate_id)

        job_posting_id = request.query_params.get('job_posting_id')
        if job_posting_id:
            qs = qs.filter(job_posting_id=job_posting_id)

        qs = qs.order_by('-total_score')

        page = int(request.query_params.get('page', 1))
        page_size = min(int(request.query_params.get('page_size', 20)), 100)
        offset = (page - 1) * page_size
        total = qs.count()
        results = qs[offset:offset + page_size]

        return Response({
            'count': total,
            'page': page,
            'results': JobMatchScoreSerializer(results, many=True).data,
        })


class ProvidersView(APIView):
    permission_classes = [HasModulePermission]
    rbac_module = 'matching'

    def get(self, request):
        from django.conf import settings
        active = getattr(settings, 'MATCHING_PROVIDER', 'rule_based')
        return Response({
            'active': active,
            'available': ProviderRegistry.list_providers(),
        })
