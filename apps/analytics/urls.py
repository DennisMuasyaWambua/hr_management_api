from django.urls import path

from .views import (HeadcountView, LeaveAnalyticsView, OverviewView,
                    PayrollAnalyticsView, PlacementAnalyticsView,
                    RecruitmentView)

urlpatterns = [
    path('analytics/overview/', OverviewView.as_view(), name='analytics-overview'),
    path('analytics/headcount/', HeadcountView.as_view(), name='analytics-headcount'),
    path('analytics/recruitment/', RecruitmentView.as_view(), name='analytics-recruitment'),
    path('analytics/payroll/', PayrollAnalyticsView.as_view(), name='analytics-payroll'),
    path('analytics/leave/', LeaveAnalyticsView.as_view(), name='analytics-leave'),
    path('analytics/placements/', PlacementAnalyticsView.as_view(),
         name='analytics-placements'),
]
