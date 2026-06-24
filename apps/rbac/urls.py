from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    MePermissionsView, PermissionViewSet, OrganizationViewSet,
    RoleViewSet, UserRoleViewSet, OrganigramNodeViewSet,
)

# NOTE: prefixed ``orgrbac/`` (not ``rbac/``) because apps.core already owns
# rbac/roles and rbac/permissions for the legacy RBAC — those would otherwise
# shadow these endpoints since apps.core.urls is included first.
router = DefaultRouter()
router.register('orgrbac/organizations', OrganizationViewSet, basename='orgrbac-organizations')
router.register('orgrbac/permissions', PermissionViewSet, basename='orgrbac-permissions')
router.register('orgrbac/roles', RoleViewSet, basename='orgrbac-roles')
router.register('orgrbac/user-roles', UserRoleViewSet, basename='orgrbac-user-roles')
router.register('orgrbac/organigram', OrganigramNodeViewSet, basename='orgrbac-organigram')

urlpatterns = [
    path('orgrbac/me/', MePermissionsView.as_view(), name='orgrbac-me'),
    path('', include(router.urls)),
]
