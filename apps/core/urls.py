from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (AppUserViewSet, AuditLogViewSet,
                    NotificationTemplateViewSet, NotificationViewSet,
                    OneTapApprovalView, PermissionViewSet, RoleViewSet,
                    UserRoleAssignmentViewSet)
from .views_auth import SendOTPView, VerifyOTPView

router = DefaultRouter()
router.register('users', AppUserViewSet, basename='users')
router.register('rbac/roles', RoleViewSet, basename='rbac-roles')
router.register('rbac/permissions', PermissionViewSet, basename='rbac-permissions')
router.register('rbac/assignments', UserRoleAssignmentViewSet, basename='rbac-assignments')
router.register('notifications/templates', NotificationTemplateViewSet,
                basename='notification-templates')
router.register('notifications', NotificationViewSet, basename='notifications')
router.register('audit', AuditLogViewSet, basename='audit')

urlpatterns = router.urls + [
    path('one-tap/<str:token>/', OneTapApprovalView.as_view(), name='one-tap'),
    path('auth/send-otp/', SendOTPView.as_view(), name='auth-send-otp'),
    path('auth/verify-otp/', VerifyOTPView.as_view(), name='auth-verify-otp'),
]
