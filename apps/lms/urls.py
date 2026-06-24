from rest_framework.routers import DefaultRouter

from .views import (AssessmentViewSet, CourseCertificateViewSet,
                    CourseEnrollmentViewSet, CourseModuleViewSet,
                    CourseViewSet, LearningPathViewSet, LessonViewSet)

router = DefaultRouter()
router.register('lms/courses', CourseViewSet, basename='lms-courses')
router.register('lms/modules', CourseModuleViewSet, basename='lms-modules')
router.register('lms/lessons', LessonViewSet, basename='lms-lessons')
router.register('lms/assessments', AssessmentViewSet, basename='lms-assessments')
router.register('lms/learning-paths', LearningPathViewSet, basename='lms-paths')
router.register('lms/enrollments', CourseEnrollmentViewSet, basename='lms-enrollments')
router.register('lms/certificates', CourseCertificateViewSet, basename='lms-certificates')

urlpatterns = router.urls
