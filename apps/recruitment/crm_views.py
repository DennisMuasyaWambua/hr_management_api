import uuid

from django.db import IntegrityError
from django.db.models import Q
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.models import ServiceAuditLog
from apps.core.permissions import HasModulePermission, request_company_id, request_user_id
from apps.hr.views import CompanyScopedViewSet

from .crm_serializers import (
    CandidateActivitySerializer, CandidateNoteSerializer,
    CandidateTagAssignmentSerializer, CandidateTagSerializer,
    ReferralSerializer, TalentPoolMemberSerializer, TalentPoolSerializer,
)
from .models import (
    Candidate, CandidateActivity, CandidateNote,
    CandidateTag, CandidateTagAssignment, Referral,
    TalentPool, TalentPoolMember,
)


def _activity(candidate, event_type, description, company_id, request=None, metadata=None):
    actor_id = request_user_id(request) if request else None
    CandidateActivity.objects.create(
        company_id=company_id,
        candidate=candidate,
        event_type=event_type,
        description=description,
        actor_id=actor_id,
        metadata=metadata or {},
    )


class TalentPoolViewSet(CompanyScopedViewSet):
    queryset = TalentPool.objects.all()
    serializer_class = TalentPoolSerializer
    rbac_module = 'talent_pools'

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get('active_only') == 'true':
            qs = qs.filter(is_active=True)
        return qs.order_by('-created_at')

    def perform_create(self, serializer):
        company_id = request_company_id(self.request)
        actor_id = request_user_id(self.request)
        instance = serializer.save(company_id=company_id, created_by=actor_id)
        ServiceAuditLog.log('talent_pools.created', request=self.request,
                            object_type='TalentPool', object_id=str(instance.id),
                            company_id=company_id)

    @action(detail=True, methods=['post'], url_path='add-candidate')
    def add_candidate(self, request, pk=None):
        pool = self.get_object()
        candidate_id = request.data.get('candidate_id')
        if not candidate_id:
            return Response({'detail': 'candidate_id required.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            candidate = Candidate.objects.get(pk=candidate_id, company_id=pool.company_id)
        except Candidate.DoesNotExist:
            return Response({'detail': 'Candidate not found.'}, status=status.HTTP_404_NOT_FOUND)
        notes = request.data.get('notes', '')
        actor_id = request_user_id(request)
        try:
            member = TalentPoolMember.objects.create(
                pool=pool, candidate=candidate, added_by=actor_id, notes=notes)
        except IntegrityError:
            return Response({'detail': 'Candidate already in pool.'}, status=status.HTTP_409_CONFLICT)
        _activity(candidate, 'pool_added', f'Added to pool "{pool.name}"',
                  pool.company_id, request, {'pool_id': str(pool.id)})
        return Response(TalentPoolMemberSerializer(member).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='remove-candidate')
    def remove_candidate(self, request, pk=None):
        pool = self.get_object()
        candidate_id = request.data.get('candidate_id')
        if not candidate_id:
            return Response({'detail': 'candidate_id required.'}, status=status.HTTP_400_BAD_REQUEST)
        deleted, _ = TalentPoolMember.objects.filter(
            pool=pool, candidate_id=candidate_id).delete()
        if not deleted:
            return Response({'detail': 'Candidate not in pool.'}, status=status.HTTP_404_NOT_FOUND)
        try:
            candidate = Candidate.objects.get(pk=candidate_id)
            _activity(candidate, 'pool_removed', f'Removed from pool "{pool.name}"',
                      pool.company_id, request, {'pool_id': str(pool.id)})
        except Candidate.DoesNotExist:
            pass
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['get'])
    def members(self, request, pk=None):
        pool = self.get_object()
        qs = TalentPoolMember.objects.filter(pool=pool).select_related('candidate')
        serializer = TalentPoolMemberSerializer(qs, many=True)
        return Response({'count': qs.count(), 'results': serializer.data})


class CandidateTagViewSet(CompanyScopedViewSet):
    queryset = CandidateTag.objects.all()
    serializer_class = CandidateTagSerializer
    rbac_module = 'recruitment'

    def get_queryset(self):
        return super().get_queryset().order_by('name')

    def perform_create(self, serializer):
        company_id = request_company_id(self.request)
        serializer.save(company_id=company_id)


class CandidateTagAssignmentViewSet(CompanyScopedViewSet):
    queryset = CandidateTagAssignment.objects.select_related('tag', 'candidate').all()
    serializer_class = CandidateTagAssignmentSerializer
    rbac_module = 'recruitment'
    http_method_names = ['get', 'post', 'delete', 'head', 'options']

    def get_queryset(self):
        company_id = request_company_id(self.request)
        qs = CandidateTagAssignment.objects.select_related('tag', 'candidate')
        if company_id:
            qs = qs.filter(tag__company_id=company_id)
        candidate_id = self.request.query_params.get('candidate_id')
        if candidate_id:
            qs = qs.filter(candidate_id=candidate_id)
        return qs

    def perform_create(self, serializer):
        instance = serializer.save()
        company_id = instance.tag.company_id
        _activity(instance.candidate, 'tag_added',
                  f'Tag "{instance.tag.name}" added',
                  company_id, self.request, {'tag_id': str(instance.tag_id)})

    def perform_destroy(self, instance):
        company_id = instance.tag.company_id
        candidate = instance.candidate
        tag_name = instance.tag.name
        tag_id = str(instance.tag_id)
        instance.delete()
        _activity(candidate, 'tag_removed', f'Tag "{tag_name}" removed',
                  company_id, self.request, {'tag_id': tag_id})


class CandidateNoteViewSet(CompanyScopedViewSet):
    queryset = CandidateNote.objects.all()
    serializer_class = CandidateNoteSerializer
    rbac_module = 'recruitment'

    def get_queryset(self):
        qs = super().get_queryset()
        candidate_id = self.request.query_params.get('candidate_id')
        if candidate_id:
            qs = qs.filter(candidate_id=candidate_id)
        return qs

    def perform_create(self, serializer):
        company_id = request_company_id(self.request)
        actor_id = request_user_id(self.request)
        instance = serializer.save(company_id=company_id, author_id=actor_id)
        _activity(instance.candidate, 'note_added',
                  f'{instance.get_note_type_display()} note added',
                  company_id, self.request, {'note_id': str(instance.id)})


class CandidateActivityViewSet(CompanyScopedViewSet):
    queryset = CandidateActivity.objects.all()
    serializer_class = CandidateActivitySerializer
    rbac_module = 'recruitment'
    http_method_names = ['get', 'head', 'options']

    def get_queryset(self):
        company_id = request_company_id(self.request)
        qs = CandidateActivity.objects.all()
        if company_id:
            qs = qs.filter(company_id=company_id)
        candidate_id = self.request.query_params.get('candidate_id')
        if candidate_id:
            qs = qs.filter(candidate_id=candidate_id)
        return qs


class ReferralViewSet(CompanyScopedViewSet):
    queryset = Referral.objects.select_related('candidate').all()
    serializer_class = ReferralSerializer
    rbac_module = 'referrals'

    def get_queryset(self):
        qs = super().get_queryset()
        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
        candidate_id = self.request.query_params.get('candidate_id')
        if candidate_id:
            qs = qs.filter(candidate_id=candidate_id)
        return qs

    def perform_create(self, serializer):
        company_id = request_company_id(self.request)
        instance = serializer.save(company_id=company_id)
        _activity(instance.candidate, 'referral_submitted',
                  f'Referred by {instance.referrer_name}',
                  company_id, self.request,
                  {'referral_id': str(instance.id), 'referrer_email': instance.referrer_email})


class CandidateSearchView(APIView):
    permission_classes = [HasModulePermission]
    rbac_module = 'recruitment'

    def get(self, request):
        company_id = request_company_id(request)
        if not company_id:
            return Response({'detail': 'X-Company-Id header required.'},
                            status=status.HTTP_400_BAD_REQUEST)

        qs = Candidate.objects.filter(company_id=company_id, is_deleted=False)

        q = request.query_params.get('q')
        if q:
            qs = qs.filter(
                Q(full_name__icontains=q) |
                Q(email__icontains=q) |
                Q(skills__icontains=q)
            )

        skills_param = request.query_params.get('skills')
        if skills_param:
            skill_list = [s.strip() for s in skills_param.split(',') if s.strip()]
            for skill in skill_list:
                qs = qs.filter(skills__icontains=skill)

        location = request.query_params.get('location')
        if location:
            qs = qs.filter(location__icontains=location)

        exp_min = request.query_params.get('experience_min')
        if exp_min:
            qs = qs.filter(experience_years__gte=int(exp_min))

        exp_max = request.query_params.get('experience_max')
        if exp_max:
            qs = qs.filter(experience_years__lte=int(exp_max))

        education_level = request.query_params.get('education_level')
        if education_level:
            qs = qs.filter(education_level=education_level)

        availability_before = request.query_params.get('availability_before')
        if availability_before:
            qs = qs.filter(availability_date__lte=availability_before)

        is_passive = request.query_params.get('is_passive')
        if is_passive in ('true', 'false'):
            qs = qs.filter(is_passive=(is_passive == 'true'))

        stage = request.query_params.get('stage')
        if stage:
            qs = qs.filter(current_stage=stage)

        pool_id = request.query_params.get('pool_id')
        if pool_id:
            qs = qs.filter(pool_memberships__pool_id=pool_id)

        tag_ids_param = request.query_params.get('tag_ids')
        if tag_ids_param:
            tag_ids = [t.strip() for t in tag_ids_param.split(',') if t.strip()]
            qs = qs.filter(tag_assignments__tag_id__in=tag_ids)

        qs = qs.distinct()

        page = int(request.query_params.get('page', 1))
        page_size = min(int(request.query_params.get('page_size', 20)), 100)
        offset = (page - 1) * page_size
        total = qs.count()
        candidates = qs.order_by('-created_at')[offset:offset + page_size]

        from .serializers import CandidateSerializer
        data = CandidateSerializer(candidates, many=True).data
        return Response({
            'count': total,
            'page': page,
            'page_size': page_size,
            'results': data,
        })
