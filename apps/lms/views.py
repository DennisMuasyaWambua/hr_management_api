import uuid
from datetime import datetime

from django.db import IntegrityError
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.permissions import HasModulePermission, request_company_id
from apps.hr.views import CompanyScopedViewSet

from .models import (Assessment, AssessmentAttempt, AssessmentQuestion,
                     Course, CourseEnrollment, CourseModule, CourseCertificate,
                     LearningPath, LearningPathCourse, Lesson, LessonProgress)
from .serializers import (AssessmentAttemptSerializer, AssessmentQuestionSerializer,
                          AssessmentSerializer, AssessmentWriteSerializer,
                          CourseCertificateSerializer, CourseDetailSerializer,
                          CourseEnrollmentSerializer, CourseListSerializer,
                          CourseModuleSerializer, CourseModuleWriteSerializer,
                          LearningPathSerializer, LessonProgressSerializer,
                          LessonSerializer)


def _company(request):
    return request_company_id(request)


class CourseViewSet(CompanyScopedViewSet):
    rbac_module = 'lms'
    queryset = Course.objects.filter(is_deleted=False)

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return CourseDetailSerializer
        return CourseListSerializer

    def perform_destroy(self, instance):
        instance.is_deleted = True
        instance.save(update_fields=['is_deleted', 'updated_at'])

    @action(detail=True, methods=['get', 'post'], url_path='modules')
    def modules(self, request, pk=None):
        course = self.get_object()
        if request.method == 'GET':
            qs = CourseModule.objects.filter(
                course=course, is_deleted=False).order_by('order')
            return Response(CourseModuleSerializer(qs, many=True).data)

        serializer = CourseModuleWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        company_id = _company(request)
        module = serializer.save(
            course=course,
            company_id=company_id,
            tenant_id=course.tenant_id,
        )
        return Response(CourseModuleWriteSerializer(module).data,
                        status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get', 'post'], url_path='assessments')
    def assessments(self, request, pk=None):
        course = self.get_object()
        if request.method == 'GET':
            qs = Assessment.objects.filter(course=course, is_deleted=False)
            return Response(AssessmentSerializer(qs, many=True).data)

        serializer = AssessmentWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        company_id = _company(request)
        assessment = serializer.save(
            course=course,
            company_id=company_id,
            tenant_id=course.tenant_id,
        )
        return Response(AssessmentWriteSerializer(assessment).data,
                        status=status.HTTP_201_CREATED)


class CourseModuleViewSet(CompanyScopedViewSet):
    rbac_module = 'lms'
    queryset = CourseModule.objects.filter(is_deleted=False)

    def get_serializer_class(self):
        if self.request.method in ('GET', 'HEAD'):
            return CourseModuleSerializer
        return CourseModuleWriteSerializer

    def perform_destroy(self, instance):
        instance.is_deleted = True
        instance.save(update_fields=['is_deleted', 'updated_at'])

    @action(detail=True, methods=['get', 'post'], url_path='lessons')
    def lessons(self, request, pk=None):
        module = self.get_object()
        if request.method == 'GET':
            qs = Lesson.objects.filter(module=module, is_deleted=False).order_by('order')
            return Response(LessonSerializer(qs, many=True).data)

        serializer = LessonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        company_id = _company(request)
        lesson = serializer.save(
            module=module,
            company_id=company_id,
            tenant_id=module.tenant_id,
        )
        return Response(LessonSerializer(lesson).data, status=status.HTTP_201_CREATED)


class LessonViewSet(CompanyScopedViewSet):
    rbac_module = 'lms'
    queryset = Lesson.objects.filter(is_deleted=False)
    serializer_class = LessonSerializer

    def perform_destroy(self, instance):
        instance.is_deleted = True
        instance.save(update_fields=['is_deleted', 'updated_at'])


class AssessmentViewSet(CompanyScopedViewSet):
    rbac_module = 'lms'
    queryset = Assessment.objects.filter(is_deleted=False)

    def get_serializer_class(self):
        if self.request.method in ('GET', 'HEAD'):
            return AssessmentSerializer
        return AssessmentWriteSerializer

    def perform_destroy(self, instance):
        instance.is_deleted = True
        instance.save(update_fields=['is_deleted', 'updated_at'])

    @action(detail=True, methods=['get', 'post'], url_path='questions')
    def questions(self, request, pk=None):
        assessment = self.get_object()
        if request.method == 'GET':
            qs = AssessmentQuestion.objects.filter(
                assessment=assessment).order_by('order')
            return Response(AssessmentQuestionSerializer(qs, many=True).data)

        serializer = AssessmentQuestionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        company_id = _company(request)
        question = serializer.save(
            assessment=assessment,
            company_id=company_id,
            tenant_id=assessment.tenant_id,
        )
        return Response(AssessmentQuestionSerializer(question).data,
                        status=status.HTTP_201_CREATED)


class LearningPathViewSet(CompanyScopedViewSet):
    rbac_module = 'lms'
    queryset = LearningPath.objects.filter(is_deleted=False)
    serializer_class = LearningPathSerializer

    def perform_destroy(self, instance):
        instance.is_deleted = True
        instance.save(update_fields=['is_deleted', 'updated_at'])

    @action(detail=True, methods=['post'], url_path='add-course')
    def add_course(self, request, pk=None):
        path = self.get_object()
        course_id = request.data.get('course_id')
        order = request.data.get('order', 0)
        if not course_id:
            return Response({'detail': 'course_id required'},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            course = Course.objects.get(
                id=course_id, company_id=_company(request), is_deleted=False)
        except Course.DoesNotExist:
            return Response({'detail': 'Course not found'},
                            status=status.HTTP_404_NOT_FOUND)
        try:
            lpc = LearningPathCourse.objects.create(
                path=path, course=course, order=order)
        except IntegrityError:
            return Response({'detail': 'Course already in path'},
                            status=status.HTTP_409_CONFLICT)
        return Response({'id': str(lpc.id), 'order': lpc.order},
                        status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='remove-course')
    def remove_course(self, request, pk=None):
        path = self.get_object()
        course_id = request.data.get('course_id')
        deleted, _ = LearningPathCourse.objects.filter(
            path=path, course_id=course_id).delete()
        if not deleted:
            return Response({'detail': 'Course not in path'},
                            status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)


class CourseEnrollmentViewSet(CompanyScopedViewSet):
    rbac_module = 'lms'
    serializer_class = CourseEnrollmentSerializer

    def get_queryset(self):
        company_id = _company(self.request)
        return CourseEnrollment.objects.filter(
            company_id=company_id).select_related('course', 'certificate')

    def perform_create(self, serializer):
        company_id = _company(self.request)
        employee_id = self.request.data.get('employee_id') or uuid.uuid4()
        try:
            enrollment = serializer.save(
                company_id=company_id,
                tenant_id=company_id,
                employee_id=employee_id,
            )
        except IntegrityError:
            from rest_framework.exceptions import ValidationError
            raise ValidationError('Employee already enrolled in this course.')

    def create(self, request, *args, **kwargs):
        course_id = request.data.get('course')
        if not course_id:
            return Response({'detail': 'course required'},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            Course.objects.get(
                id=course_id, company_id=_company(request), is_deleted=False)
        except Course.DoesNotExist:
            return Response({'detail': 'Course not found'},
                            status=status.HTTP_404_NOT_FOUND)
        return super().create(request, *args, **kwargs)

    @action(detail=True, methods=['post'], url_path='complete-lesson')
    def complete_lesson(self, request, pk=None):
        enrollment = self.get_object()
        lesson_id = request.data.get('lesson_id')
        time_spent = int(request.data.get('time_spent_s', 0))

        if not lesson_id:
            return Response({'detail': 'lesson_id required'},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            lesson = Lesson.objects.get(
                id=lesson_id, is_deleted=False,
                module__course=enrollment.course)
        except Lesson.DoesNotExist:
            return Response({'detail': 'Lesson not found in this course'},
                            status=status.HTTP_404_NOT_FOUND)

        progress, _ = LessonProgress.objects.get_or_create(
            enrollment=enrollment, lesson=lesson)
        if not progress.completed:
            progress.completed = True
            progress.completed_at = timezone.now()
            progress.time_spent_s = time_spent
            progress.save(update_fields=['completed', 'completed_at', 'time_spent_s'])

        self._refresh_progress(enrollment)
        enrollment.refresh_from_db()
        return Response(CourseEnrollmentSerializer(enrollment).data)

    @action(detail=True, methods=['post'], url_path='submit-assessment')
    def submit_assessment(self, request, pk=None):
        enrollment = self.get_object()
        assessment_id = request.data.get('assessment_id')
        answers = request.data.get('answers', {})

        if not assessment_id:
            return Response({'detail': 'assessment_id required'},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            assessment = Assessment.objects.get(
                id=assessment_id, course=enrollment.course, is_deleted=False)
        except Assessment.DoesNotExist:
            return Response({'detail': 'Assessment not found'},
                            status=status.HTTP_404_NOT_FOUND)

        attempt_count = AssessmentAttempt.objects.filter(
            enrollment=enrollment, assessment=assessment).count()
        if attempt_count >= assessment.max_attempts:
            return Response({'detail': 'Maximum attempts reached'},
                            status=status.HTTP_409_CONFLICT)

        score, passed = self._grade(assessment, answers)
        attempt = AssessmentAttempt.objects.create(
            enrollment=enrollment,
            assessment=assessment,
            attempt_no=attempt_count + 1,
            score=score,
            passed=passed,
            answers=answers,
            submitted_at=timezone.now(),
            company_id=enrollment.company_id,
            tenant_id=enrollment.tenant_id,
        )

        if passed and enrollment.status != 'completed':
            enrollment.score = score
            enrollment.status = 'completed'
            enrollment.completed_at = timezone.now()
            enrollment.progress_pct = 100.0
            enrollment.save(update_fields=['score', 'status', 'completed_at',
                                           'progress_pct', 'updated_at'])
            self._issue_certificate(enrollment)

        return Response({
            'attempt_no': attempt.attempt_no,
            'score': score,
            'passed': passed,
        }, status=status.HTTP_201_CREATED)

    @staticmethod
    def _grade(assessment, answers):
        questions = list(assessment.questions.all())
        if not questions:
            return 0.0, False
        total_points = sum(q.points for q in questions)
        earned = 0.0
        for q in questions:
            submitted = answers.get(str(q.id))
            correct = q.answer
            if q.question_type in ('mcq', 'true_false'):
                if submitted == correct:
                    earned += q.points
        score = round(earned / total_points * 100, 2) if total_points else 0.0
        return score, score >= assessment.pass_score

    @staticmethod
    def _issue_certificate(enrollment):
        if not hasattr(enrollment, 'certificate') or \
                not CourseCertificate.objects.filter(enrollment=enrollment).exists():
            cert_no = f'CERT-{str(enrollment.id)[:8].upper()}-{str(uuid.uuid4())[:4].upper()}'
            CourseCertificate.objects.create(
                enrollment=enrollment,
                certificate_no=cert_no,
                company_id=enrollment.company_id,
                tenant_id=enrollment.tenant_id,
            )

    @staticmethod
    def _refresh_progress(enrollment):
        total_lessons = Lesson.objects.filter(
            module__course=enrollment.course,
            module__is_deleted=False,
            is_deleted=False,
        ).count()
        done = LessonProgress.objects.filter(
            enrollment=enrollment, completed=True).count()
        pct = round(done / total_lessons * 100, 2) if total_lessons else 0.0
        new_status = enrollment.status
        if pct > 0 and enrollment.status == 'enrolled':
            new_status = 'in_progress'
        enrollment.progress_pct = pct
        enrollment.status = new_status
        enrollment.save(update_fields=['progress_pct', 'status', 'updated_at'])


class CourseCertificateViewSet(CompanyScopedViewSet):
    rbac_module = 'lms'
    http_method_names = ['get', 'head', 'options']
    serializer_class = CourseCertificateSerializer

    def get_queryset(self):
        return CourseCertificate.objects.filter(
            company_id=_company(self.request)).select_related(
            'enrollment__course')
