from rest_framework.routers import DefaultRouter

from .views import (CompetencyRatingViewSet, CompetencyViewSet,
                    DevelopmentPlanItemViewSet, DevelopmentPlanViewSet,
                    FeedbackRequestViewSet, PerformanceGoalViewSet)

router = DefaultRouter()
router.register('performance/goals', PerformanceGoalViewSet, basename='perf-goals')
router.register('performance/competencies', CompetencyViewSet, basename='perf-competencies')
router.register('performance/competency-ratings', CompetencyRatingViewSet,
                basename='perf-competency-ratings')
router.register('performance/development-plans', DevelopmentPlanViewSet,
                basename='perf-dev-plans')
router.register('performance/plan-items', DevelopmentPlanItemViewSet,
                basename='perf-plan-items')
router.register('performance/feedback-requests', FeedbackRequestViewSet,
                basename='perf-feedback-requests')

urlpatterns = router.urls
