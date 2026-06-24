from django.urls import path

from . import views

urlpatterns = [
    path('actions/', views.ActionListView.as_view(), name='action-list'),
    path('actions/summary/', views.ActionSummaryView.as_view(), name='action-summary'),
    path('actions/high-priority/', views.ActionHighPriorityView.as_view(), name='action-high-priority'),
    path('actions/overdue/', views.ActionOverdueView.as_view(), name='action-overdue'),
    path('actions/upcoming/', views.ActionUpcomingView.as_view(), name='action-upcoming'),
    path('actions/<str:action_id>/dismiss/', views.ActionDismissView.as_view(), name='action-dismiss'),
    path('actions/<str:action_id>/escalate/', views.ActionEscalateView.as_view(), name='action-escalate'),
]
