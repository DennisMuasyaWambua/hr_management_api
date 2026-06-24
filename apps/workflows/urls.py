from django.urls import path

from . import views

urlpatterns = [
    path('workflows/', views.WorkflowDefinitionListView.as_view(), name='workflow-list'),
    path('workflows/<uuid:pk>/', views.WorkflowDefinitionDetailView.as_view(), name='workflow-detail'),
    path('workflows/<uuid:pk>/activate/', views.WorkflowActivateView.as_view(), name='workflow-activate'),
    path('workflows/<uuid:pk>/deactivate/', views.WorkflowDeactivateView.as_view(), name='workflow-deactivate'),
    path('workflows/executions/', views.WorkflowExecutionListView.as_view(), name='workflow-execution-list'),
    path('workflows/executions/<uuid:pk>/', views.WorkflowExecutionDetailView.as_view(), name='workflow-execution-detail'),
    path('workflows/templates/', views.WorkflowTemplateListView.as_view(), name='workflow-template-list'),
    path('workflows/tasks/', views.WorkflowTaskListView.as_view(), name='workflow-task-list'),
    path('workflows/tasks/<uuid:pk>/', views.WorkflowTaskDetailView.as_view(), name='workflow-task-detail'),
    path('workflows/tasks/<uuid:pk>/complete/', views.WorkflowTaskCompleteView.as_view(), name='workflow-task-complete'),
]
