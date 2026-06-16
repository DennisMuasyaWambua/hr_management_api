from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (AlertLogView, AlertMatchingView, AlertSubscribeView,
                    AlertUnsubscribeView, CandidateViewSet, JobPostingViewSet,
                    PublicApplyView, PublicJobDetailView, PublicJobListView,
                    PublicTrackView)

router = DefaultRouter()
router.register('job-postings', JobPostingViewSet, basename='job-postings')
router.register('candidates', CandidateViewSet, basename='candidates')

urlpatterns = router.urls + [
    path('careers/jobs/', PublicJobListView.as_view(), name='careers-jobs'),
    path('careers/jobs/<uuid:pk>/', PublicJobDetailView.as_view(), name='careers-job-detail'),
    path('careers/jobs/<uuid:pk>/apply/', PublicApplyView.as_view(), name='careers-apply'),
    path('careers/applications/track/<uuid:token>/', PublicTrackView.as_view(),
         name='careers-track'),
    path('careers/alerts/subscribe/', AlertSubscribeView.as_view(),
         name='careers-alert-subscribe'),
    path('careers/alerts/unsubscribe/', AlertUnsubscribeView.as_view(),
         name='careers-alert-unsubscribe'),
    path('careers/alerts/matching/', AlertMatchingView.as_view(),
         name='careers-alert-matching'),
    path('careers/alerts/logs/', AlertLogView.as_view(), name='careers-alert-logs'),
]
