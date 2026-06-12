from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (AuditLogViewSet, NotificationTemplateViewSet,
                    NotificationViewSet, OneTapApprovalView, PermissionViewSet,
                    RoleViewSet, UserRoleAssignmentViewSet)

router = DefaultRouter()
router.register('rbac/roles', RoleViewSet, basename='rbac-roles')
router.register('rbac/permissions', PermissionViewSet, basename='rbac-permissions')
router.register('rbac/assignments', UserRoleAssignmentViewSet, basename='rbac-assignments')
router.register('notifications/templates', NotificationTemplateViewSet,
                basename='notification-templates')
router.register('notifications', NotificationViewSet, basename='notifications')
router.register('audit', AuditLogViewSet, basename='audit')

urlpatterns = router.urls + [
    path('one-tap/<str:token>/', OneTapApprovalView.as_view(), name='one-tap'),
]
