from django.urls import path
from rest_framework.routers import DefaultRouter

from .crm_views import (CandidateActivityViewSet, CandidateNoteViewSet,
                        CandidateSearchView, CandidateTagAssignmentViewSet,
                        CandidateTagViewSet, ReferralViewSet, TalentPoolViewSet)
from .views import (AlertLogView, AlertMatchingView, AlertSubscribeView,
                    AlertUnsubscribeView, CandidateViewSet, InterviewViewSet,
                    JobPostingViewSet, PublicApplyView, PublicJobDetailView,
                    PublicJobListView, PublicTrackView)

router = DefaultRouter()
router.register('job-postings', JobPostingViewSet, basename='job-postings')
router.register('candidates', CandidateViewSet, basename='candidates')
router.register('interviews', InterviewViewSet, basename='interviews')
router.register('talent-pools', TalentPoolViewSet, basename='talent-pools')
router.register('candidate-tags', CandidateTagViewSet, basename='candidate-tags')
router.register('candidate-tag-assignments', CandidateTagAssignmentViewSet,
                basename='candidate-tag-assignments')
router.register('candidate-notes', CandidateNoteViewSet, basename='candidate-notes')
router.register('candidate-activities', CandidateActivityViewSet,
                basename='candidate-activities')
router.register('referrals', ReferralViewSet, basename='referrals')

urlpatterns = router.urls + [
    path('candidate-search/', CandidateSearchView.as_view(), name='candidate-search'),
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
