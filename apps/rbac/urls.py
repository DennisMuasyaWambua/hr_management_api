from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    MePermissionsView, PermissionViewSet, OrganizationViewSet,
    RoleViewSet, UserRoleViewSet, OrganigramNodeViewSet,
)

router = DefaultRouter()
router.register('rbac/organizations', OrganizationViewSet, basename='rbac-organizations')
router.register('rbac/permissions', PermissionViewSet, basename='rbac-permissions')
router.register('rbac/roles', RoleViewSet, basename='rbac-roles')
router.register('rbac/user-roles', UserRoleViewSet, basename='rbac-user-roles')
router.register('rbac/organigram', OrganigramNodeViewSet, basename='rbac-organigram')

urlpatterns = [
    path('rbac/me/', MePermissionsView.as_view(), name='rbac-me'),
    path('', include(router.urls)),
]
