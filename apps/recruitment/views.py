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
import logging

from django.contrib.auth import get_user_model
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.models import ServiceAuditLog
from apps.core.permissions import request_company_id, request_user_id
from apps.hr.views import CompanyScopedViewSet

logger = logging.getLogger(__name__)

from .models import Candidate, Interview, JobAlert, JobAlertLog, JobPosting
from .serializers import (CandidateSerializer, CandidateTrackSerializer,
                          ConvertCandidateSerializer, InterviewSerializer,
                          JobAlertSerializer, JobPostingPublicSerializer,
                          JobPostingSerializer)


# ---------------------------------------------------------------------------
# Notification helpers
# ---------------------------------------------------------------------------

def _notify_interview_scheduled(interview):
    """Notify candidate + interviewers when an interview is scheduled or auto-created."""
    from apps.core.models import AppUser
    from apps.core.services import notifications as notif

    candidate = interview.candidate
    recipients = [{'email': candidate.email, 'full_name': candidate.full_name}]

    if interview.interviewer_ids:
        for interviewer in AppUser.objects.filter(
            id__in=interview.interviewer_ids, is_deleted=False
        ).values('email', 'full_name'):
            recipients.append(interviewer)

    try:
        notif.notify(
            'interview.scheduled',
            recipients,
            {
                'candidate_name': candidate.full_name,
                'interview_type': interview.get_interview_type_display(),
                'scheduled_at': interview.scheduled_at.strftime('%d %b %Y %H:%M'),
                'location': interview.location or 'To be confirmed',
                'job_title': interview.job_posting.title,
            },
            company_id=interview.company_id,
            related=('Interview', str(interview.id)),
        )
    except Exception:
        logger.warning(
            'interview.scheduled notification failed for interview %s',
            interview.id, exc_info=True,
        )


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
        new_stage = request.data.get('current_stage') or request.data.get('stage')
        if new_stage:
            candidate.current_stage = new_stage
        if 'rejection_reason' in request.data:
            candidate.rejection_reason = request.data['rejection_reason']
        if 'notes' in request.data:
            candidate.notes = request.data['notes']
        candidate.save()

        # Auto-create a scheduled Interview stub when advancing to an interview stage.
        if new_stage in ('interview_l1', 'interview_l2'):
            interview_type = 'l1' if new_stage == 'interview_l1' else 'l2'
            scheduled_at_raw = request.data.get('scheduled_at')
            if scheduled_at_raw:
                interview = Interview.objects.create(
                    candidate=candidate,
                    job_posting=candidate.job_posting,
                    interview_type=interview_type,
                    status='scheduled',
                    scheduled_at=scheduled_at_raw,
                    location=request.data.get('location', ''),
                    interviewer_ids=request.data.get('interviewer_ids') or [],
                    notes=request.data.get('notes', ''),
                    company_id=candidate.company_id,
                    tenant_id=candidate.tenant_id,
                    created_by=request_user_id(request),
                )
                _notify_interview_scheduled(interview)

        return Response(CandidateSerializer(candidate).data)

    @action(detail=True, methods=['post'])
    def convert(self, request, pk=None):
        """
        POST /api/candidates/{id}/convert/

        Convert a hired candidate into an EmployeeProfile + AppUser.
        Idempotent: returns 409 if already converted.
        Atomic: all writes succeed or all roll back.
        """
        candidate = self.get_object()

        # Idempotency — already converted
        if candidate.converted_at is not None:
            return Response({
                'error': 'This candidate has already been converted to an employee.',
                'employee_profile_id': (
                    str(candidate.converted_employee_id)
                    if candidate.converted_employee_id else None
                ),
            }, status=409)

        if candidate.current_stage != 'hired':
            return Response(
                {'error': 'Only hired candidates can be converted to employees.'},
                status=400,
            )

        # Tenant guard — EmployeeProfile.tenant_id is non-nullable
        if not candidate.tenant_id:
            return Response(
                {'error': 'Candidate has no tenant_id. Cannot create employee profile. '
                          'Contact support.'},
                status=400,
            )

        serializer = ConvertCandidateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        from apps.core.models import AppUser, Role, UserRoleAssignment
        from apps.hr.models import EmployeeOnboardingDocument
        from apps.payroll.models import Company, EmployeeProfile

        company_id = candidate.company_id
        company = Company.objects.filter(id=company_id).first()
        if not company:
            return Response({'error': 'Company not found.'}, status=400)

        worker_class = data.get('worker_class', 'white_collar')
        employee_number_supplied = (data.get('employee_number') or '').strip()
        doc_types = ['contract', 'id', 'nssf', 'nhif', 'kra_pin', 'bank_details']

        with transaction.atomic():
            # Duplicate guard — inside transaction for read consistency
            if AppUser.objects.filter(email=candidate.email, is_deleted=False).exists():
                return Response(
                    {'error': 'An employee account already exists for this email.'},
                    status=409,
                )

            # Concurrency-safe employee number: lock the company row to
            # serialize concurrent converts; count is then stable.
            employee_number = employee_number_supplied
            if not employee_number:
                Company.objects.select_for_update().get(id=company_id)
                existing_count = EmployeeProfile.objects.filter(
                    company_id=company_id
                ).count()
                employee_number = f'EMP-{existing_count + 1:04d}'

            # 1. AppUser
            app_user = AppUser.objects.create(
                full_name=candidate.full_name,
                email=candidate.email,
                phone=candidate.phone,
                role='employee',
                company_id=company_id,
                tenant_id=candidate.tenant_id,
            )

            # 2. Django auth.User (unusable password — OTP login only)
            AuthUser = get_user_model()
            auth_user, _ = AuthUser.objects.get_or_create(
                username=candidate.email,
                defaults={'email': candidate.email},
            )
            auth_user.set_unusable_password()
            auth_user.save(update_fields=['password'])
            app_user.auth_user = auth_user
            app_user.save(update_fields=['auth_user', 'updated_at'])

            # 3. EmployeeProfile
            employee = EmployeeProfile.objects.create(
                user_id=app_user.id,
                employee_number=employee_number,
                company=company,
                tenant_id=candidate.tenant_id,
                job_title=data['job_title'],
                department=data.get('department') or '',
                employment_type=data['employment_type'],
                worker_class=worker_class,
                employment_status='active',
                start_date=data['start_date'],
                salary=data['salary'],
                payment_method=data['payment_method'],
            )

            # 4. Link AppUser → EmployeeProfile
            app_user.employee_id = employee.id
            app_user.save(update_fields=['employee_id', 'updated_at'])

            # 5. RBAC assignment
            role_slug = (
                'white_collar_employee' if worker_class == 'white_collar'
                else 'blue_collar_employee'
            )
            rbac_role = (
                Role.objects.filter(slug=role_slug, company_id=company_id).first()
                or Role.objects.filter(slug=role_slug, company_id__isnull=True).first()
            )
            if rbac_role:
                UserRoleAssignment.objects.get_or_create(
                    user_id=app_user.id,
                    company_id=company_id,
                    role=rbac_role,
                    defaults={
                        'tenant_id': candidate.tenant_id,
                        'assigned_by': request_user_id(request),
                    },
                )
            else:
                logger.warning(
                    'RBAC Role slug %r not found for company %s; '
                    'employee %s will have no module permissions.',
                    role_slug, company_id, employee.id,
                )

            # 6. Onboarding document stubs
            for doc_type in doc_types:
                EmployeeOnboardingDocument.objects.get_or_create(
                    employee_id=employee.id,
                    doc_type=doc_type,
                    defaults={'status': 'missing'},
                )

            # 7. Mark candidate as converted (idempotency marker)
            candidate.converted_at = timezone.now()
            candidate.converted_employee_id = employee.id
            candidate.save(update_fields=['converted_at', 'converted_employee_id', 'updated_at'])

            # 8. Audit log
            ServiceAuditLog.log(
                'candidate.converted',
                request=request,
                object_type='Candidate',
                object_id=str(candidate.id),
                company_id=company_id,
                metadata={
                    'employee_profile_id': str(employee.id),
                    'app_user_id': str(app_user.id),
                },
            )

        # Welcome notification — outside atomic block so a notification failure
        # cannot roll back the completed employee record.
        try:
            from apps.core.services import notifications as notif
            notif.notify(
                'employee.welcome',
                [{'email': candidate.email, 'full_name': candidate.full_name}],
                {
                    'full_name': candidate.full_name,
                    'employee_number': employee_number,
                    'job_title': data['job_title'],
                    'start_date': str(data['start_date']),
                    'company_name': company.name,
                },
                company_id=company_id,
            )
        except Exception:
            logger.warning(
                'employee.welcome notification failed for candidate %s',
                candidate.id, exc_info=True,
            )

        return Response({
            'employee_profile_id': str(employee.id),
            'app_user_id': str(app_user.id),
            'employee_number': employee_number,
            'onboarding_task_count': len(doc_types),
        }, status=201)


# --- Interview management -----------------------------------------------

class InterviewViewSet(CompanyScopedViewSet):
    """
    CRUD for Interview records.

    Extra actions:
      POST /{id}/complete/  — mark status=completed, record feedback
      POST /{id}/cancel/    — mark status=cancelled, record reason
    """
    queryset = Interview.objects.select_related('candidate', 'job_posting')
    serializer_class = InterviewSerializer
    rbac_module = 'recruitment'

    def get_queryset(self):
        qs = super().get_queryset()
        candidate_id = self.request.query_params.get('candidate_id')
        if candidate_id:
            qs = qs.filter(candidate_id=candidate_id)
        job_posting_id = self.request.query_params.get('job_posting_id')
        if job_posting_id:
            qs = qs.filter(job_posting_id=job_posting_id)
        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs.order_by('scheduled_at')

    def perform_create(self, serializer):
        company_id = request_company_id(self.request)
        interview = serializer.save(
            company_id=company_id,
            created_by=request_user_id(self.request),
        )
        ServiceAuditLog.log(
            'recruitment.interview_scheduled', request=self.request,
            object_type='Interview', object_id=str(interview.id),
            company_id=company_id,
        )
        _notify_interview_scheduled(interview)

    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        interview = self.get_object()
        if interview.status != 'scheduled':
            return Response(
                {'error': f'Cannot complete an interview with status "{interview.status}".'},
                status=400,
            )

        update_fields = ['status', 'completed_at', 'updated_at']
        interview.status = 'completed'
        interview.completed_at = timezone.now()

        if 'feedback_score' in request.data:
            score = request.data['feedback_score']
            if score is not None:
                try:
                    score = int(score)
                except (TypeError, ValueError):
                    return Response(
                        {'feedback_score': ['Must be an integer.']}, status=400
                    )
                if not (1 <= score <= 10):
                    return Response(
                        {'feedback_score': ['Score must be between 1 and 10.']}, status=400
                    )
            interview.feedback_score = score
            update_fields.append('feedback_score')

        if 'feedback_notes' in request.data:
            interview.feedback_notes = request.data['feedback_notes']
            update_fields.append('feedback_notes')

        interview.save(update_fields=update_fields)
        ServiceAuditLog.log(
            'recruitment.interview_completed', request=request,
            object_type='Interview', object_id=str(interview.id),
            company_id=interview.company_id,
        )
        return Response(InterviewSerializer(interview).data)

    @action(detail=True, methods=['post'])
    def no_show(self, request, pk=None):
        interview = self.get_object()
        if interview.status != 'scheduled':
            return Response(
                {'error': f'Cannot mark no-show for an interview with status "{interview.status}".'},
                status=400,
            )
        interview.status = 'no_show'
        interview.save(update_fields=['status', 'updated_at'])
        ServiceAuditLog.log(
            'recruitment.interview_no_show', request=request,
            object_type='Interview', object_id=str(interview.id),
            company_id=interview.company_id,
        )
        return Response(InterviewSerializer(interview).data)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        interview = self.get_object()
        if interview.status != 'scheduled':
            return Response(
                {'error': f'Cannot cancel an interview with status "{interview.status}".'},
                status=400,
            )
        interview.status = 'cancelled'
        interview.cancelled_at = timezone.now()
        interview.cancelled_reason = request.data.get('reason', '')
        interview.save(update_fields=['status', 'cancelled_at', 'cancelled_reason', 'updated_at'])
        ServiceAuditLog.log(
            'recruitment.interview_cancelled', request=request,
            object_type='Interview', object_id=str(interview.id),
            company_id=interview.company_id,
        )
        return Response(InterviewSerializer(interview).data)


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
