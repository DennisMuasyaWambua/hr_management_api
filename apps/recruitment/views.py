"""
Recruitment API.

Two audiences:
- Admin/dashboard CRUD (JobPostingViewSet, CandidateViewSet) — company-scoped
  + RBAC, same pattern as apps.hr (CompanyScopedViewSet).
- Public careers site (Public*View, Alert*View) — AllowAny, no auth, used by
  the careers Next.js app which used to talk to Supabase directly.

AlertMatchingView/AlertLogView are "internal" (called by the careers app's
own notify route, not by browsers) so they require authentication —
ServiceKeyAuthentication (X-Service-Key) satisfies that.
"""
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.hr.views import CompanyScopedViewSet

from .models import Candidate, JobAlert, JobAlertLog, JobPosting
from .serializers import (CandidateSerializer, CandidateTrackSerializer,
                          JobAlertSerializer, JobPostingPublicSerializer,
                          JobPostingSerializer)


# --- Admin (dashboard) -------------------------------------------------

class JobPostingViewSet(CompanyScopedViewSet):
    queryset = JobPosting.objects.filter(is_deleted=False)
    serializer_class = JobPostingSerializer
    rbac_module = 'recruitment'

    def get_queryset(self):
        from django.db.models import Q
        qs = super().get_queryset()
        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(Q(title__icontains=search) | Q(department__icontains=search))
        return qs.order_by('-created_at')

    def perform_destroy(self, instance):
        # Soft delete, consistent with the rest of this codebase.
        instance.is_deleted = True
        instance.save(update_fields=['is_deleted', 'updated_at'])


class CandidateViewSet(CompanyScopedViewSet):
    queryset = Candidate.objects.filter(is_deleted=False).select_related('job_posting')
    serializer_class = CandidateSerializer
    rbac_module = 'recruitment'

    def get_queryset(self):
        from django.db.models import Q
        qs = super().get_queryset()
        job_posting_id = self.request.query_params.get('jobPostingId') or self.request.query_params.get('job_posting_id')
        if job_posting_id:
            qs = qs.filter(job_posting_id=job_posting_id)
        stage = self.request.query_params.get('stage')
        if stage:
            qs = qs.filter(current_stage=stage)
        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(Q(full_name__icontains=search) | Q(email__icontains=search))
        return qs.order_by('-created_at')

    def perform_destroy(self, instance):
        instance.is_deleted = True
        instance.save(update_fields=['is_deleted', 'updated_at'])

    @action(detail=True, methods=['patch', 'put'])
    def stage(self, request, pk=None):
        candidate = self.get_object()
        # Accept both {current_stage} (internal convention) and {stage}
        # (the dashboard hook's field name).
        new_stage = request.data.get('current_stage') or request.data.get('stage')
        if new_stage:
            candidate.current_stage = new_stage
        if 'rejection_reason' in request.data:
            candidate.rejection_reason = request.data['rejection_reason']
        if 'notes' in request.data:
            candidate.notes = request.data['notes']
        candidate.save()
        return Response(CandidateSerializer(candidate).data)


# --- Public (careers site) ----------------------------------------------

class PublicJobListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        jobs = JobPosting.objects.filter(status='open', is_deleted=False).order_by('-created_at')
        return Response(JobPostingPublicSerializer(jobs, many=True).data)


class PublicJobDetailView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, pk):
        job = get_object_or_404(JobPosting, pk=pk, status='open', is_deleted=False)
        return Response(JobPostingPublicSerializer(job).data)


class PublicApplyView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, pk):
        job = get_object_or_404(JobPosting, pk=pk, status='open', is_deleted=False)
        email = (request.data.get('email') or '').strip().lower()
        if not email:
            return Response({'error': 'email is required'}, status=400)

        if Candidate.objects.filter(job_posting=job, email=email, is_deleted=False).exists():
            return Response({'error': 'You have already applied to this position.'}, status=409)

        consent = bool(request.data.get('data_consent', False))
        candidate = Candidate.objects.create(
            job_posting=job,
            tenant_id=job.tenant_id,
            company_id=job.company_id,
            full_name=request.data.get('full_name', ''),
            email=email,
            phone=request.data.get('phone'),
            cv_url=request.data.get('cv_url', ''),
            cv_text=request.data.get('cv_text'),
            notes=request.data.get('notes'),
            current_stage='screened',
            ai_extracted_skills=request.data.get('ai_extracted_skills') or [],
            source=request.data.get('source', 'careers_site'),
            data_consent=consent,
            consent_at=timezone.now() if consent else None,
            data_retention_months=request.data.get('data_retention_months'),
        )

        # Server-side AI scoring via GROQ — cv_text is required for scoring.
        cv_text = candidate.cv_text or ''
        if cv_text:
            from .groq_scoring import GroqScoringError, score_candidate
            try:
                scores = score_candidate(
                    job_title=job.title,
                    job_description=job.description or '',
                    cv_text=cv_text,
                )
                for field, value in scores.items():
                    setattr(candidate, field, value)
                if (candidate.ai_score is not None
                        and candidate.ai_score < job.auto_reject_threshold):
                    candidate.current_stage = 'rejected'
                    candidate.rejection_reason = (
                        f'Auto-rejected: score {candidate.ai_score:.1f} below '
                        f'threshold {job.auto_reject_threshold}')
                candidate.save()
            except GroqScoringError:
                # Scoring failure must not block the application submission.
                import logging
                logging.getLogger(__name__).warning(
                    'GROQ scoring failed for candidate %s', candidate.id, exc_info=True)

        return Response(CandidateSerializer(candidate).data, status=201)


class PublicTrackView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, token):
        candidate = get_object_or_404(
            Candidate.objects.select_related('job_posting'), tracking_token=token)
        return Response(CandidateTrackSerializer(candidate).data)


class AlertSubscribeView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = JobAlertSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({'success': True}, status=201)


class AlertUnsubscribeView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        token = request.query_params.get('token')
        if not token:
            return Response({'error': 'token is required'}, status=400)
        updated = JobAlert.objects.filter(unsubscribe_token=token).update(is_active=False)
        if not updated:
            return Response({'error': 'Alert not found'}, status=404)
        return Response({'success': True})


class AlertMatchingView(APIView):
    """Internal — careers app's notify route fetches candidate alerts to match against a job."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        alerts = JobAlert.objects.filter(is_active=True, frequency='instant')
        return Response(JobAlertSerializer(alerts, many=True).data)


class AlertLogView(APIView):
    """Internal — careers app records which alerts it actually notified."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Already-sent log entries for a job — lets the caller avoid
        re-notifying the same alert/channel when notify fires twice."""
        job_posting_id = request.query_params.get('job_posting_id')
        if not job_posting_id:
            return Response({'error': 'job_posting_id is required'}, status=400)
        logs = JobAlertLog.objects.filter(job_posting_id=job_posting_id).values('alert_id', 'channel')
        return Response(list(logs))

    def post(self, request):
        entries = request.data if isinstance(request.data, list) else [request.data]
        created = 0
        for entry in entries:
            if JobAlertLog.objects.filter(
                alert_id=entry['alert_id'], job_posting_id=entry['job_posting_id'],
                channel=entry.get('channel', 'email'),
            ).exists():
                continue
            JobAlertLog.objects.create(
                alert_id=entry['alert_id'], job_posting_id=entry['job_posting_id'],
                channel=entry.get('channel', 'email'), status=entry.get('status', 'sent'))
            created += 1
        return Response({'created': created}, status=201)
