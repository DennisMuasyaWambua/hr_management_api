"""Part B1 (/me) + Part B2 (company-admin management) RBAC API."""
from django.db import transaction
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.models import ServiceAuditLog

from .models import (
    Organization, Permission, Role, RolePermission, UserRole, OrganigramNode,
)
from .serializers import (
    OrganizationSerializer, PermissionSerializer, RoleSerializer,
    UserRoleSerializer, OrganigramNodeSerializer,
)
from .permissions import (
    HasRBACPermission, request_user_id, resolve_organization,
    resolve_permissions, user_permissions,
)

# Client role templates used to pre-populate a new company's roles (B2.2).
CLIENT_ROLE_TEMPLATES = [
    'client_admin', 'hiring_manager', 'hr_manager',
    'interview_panel_member', 'finance_approver', 'department_head',
]


def _copy_role_permissions(template_role, target_role):
    """Mirror a template role's permission grants onto a target role."""
    perm_ids = template_role.role_permissions.values_list('permission_id', flat=True)
    RolePermission.objects.bulk_create(
        [RolePermission(role=target_role, permission_id=pid) for pid in perm_ids],
        ignore_conflicts=True,
    )


class MePermissionsView(APIView):
    """GET /api/rbac/me/ — the caller's organizations, roles and permission set.

    Drives the frontend usePermission() hook and menu/button guards.
    """
    permission_classes = []  # identity comes from forwarded headers

    def get(self, request):
        uid = request_user_id(request)
        org = resolve_organization(request)
        roles = (
            UserRole.objects.filter(user_id=uid)
            .select_related('role', 'organization')
            if uid else UserRole.objects.none()
        )
        return Response({
            'user_id': uid,
            'organization': OrganizationSerializer(org).data if org else None,
            'roles': [
                {'id': str(ur.role_id), 'name': ur.role.name,
                 'organization_id': str(ur.organization_id)}
                for ur in roles
            ],
            'permissions': sorted(user_permissions(request)),
            'is_super_admin': any(ur.role.name == 'super_admin' for ur in roles),
        })


class PermissionViewSet(viewsets.ReadOnlyModelViewSet):
    """Catalogue of permissions — rows/columns for the matrix UI."""
    queryset = Permission.objects.all()
    serializer_class = PermissionSerializer
    permission_classes = [HasRBACPermission]
    required_permissions = {'default': 'roles.manage'}
    pagination_class = None


class OrganizationViewSet(viewsets.ModelViewSet):
    serializer_class = OrganizationSerializer
    permission_classes = [HasRBACPermission]
    required_permissions = {'default': 'organization.manage', 'list': 'organization.manage'}

    def get_queryset(self):
        qs = Organization.objects.all()
        type_ = self.request.query_params.get('type')
        if type_:
            qs = qs.filter(type=type_.upper())
        return qs

    @transaction.atomic
    def perform_create(self, serializer):
        org = serializer.save()
        # New partner companies default to CLIENT.
        if not org.type:
            org.type = Organization.CLIENT
            org.save(update_fields=['type'])
        # B2.1 — auto-provision a client_admin role for the new company.
        template = Role.objects.filter(name='client_admin', organization=None).first()
        admin_role = Role.objects.create(
            name='client_admin', organization=org, is_system_role=False,
            description='Company administrator',
        )
        if template:
            _copy_role_permissions(template, admin_role)
        ServiceAuditLog.log(
            'rbac.organization_created', request=self.request,
            object_type='organization', object_id=str(org.id),
            metadata={'name': org.name, 'type': org.type},
        )

    @action(detail=True, methods=['post'], url_path='seed-roles')
    def seed_roles(self, request, pk=None):
        """Pre-populate this company with the client role templates (B2.2)."""
        org = self.get_object()
        created = []
        for slug in CLIENT_ROLE_TEMPLATES:
            template = Role.objects.filter(name=slug, organization=None).first()
            role, was_created = Role.objects.get_or_create(
                name=slug, organization=org,
                defaults={'description': template.description if template else ''},
            )
            if was_created and template:
                _copy_role_permissions(template, role)
            if was_created:
                created.append(slug)
        return Response({'created': created})


class RoleViewSet(viewsets.ModelViewSet):
    serializer_class = RoleSerializer
    permission_classes = [HasRBACPermission]
    required_permissions = {'default': 'roles.manage', 'list': 'roles.manage',
                            'retrieve': 'roles.manage'}

    def get_queryset(self):
        qs = Role.objects.all()
        org_id = self.request.query_params.get('organization')
        if org_id:
            # Company-scoped roles + the system templates to clone from.
            qs = qs.filter(organization_id=org_id)
        elif self.request.query_params.get('system') == 'true':
            qs = qs.filter(organization__isnull=True)
        return qs

    @action(detail=True, methods=['get', 'put'], url_path='permissions')
    def permissions(self, request, pk=None):
        """B2.3 — the permissions matrix for a role.

        GET  -> {'permissions': ['payroll.view', ...]}
        PUT  body {'permissions': ['payroll.view', 'payroll.approve']}
             replaces the role's grants wholesale (immediate effect).
        """
        role = self.get_object()
        if request.method == 'GET':
            return Response({'permissions': [
                rp.permission.code for rp in
                role.role_permissions.select_related('permission')
            ]})

        codes = set(request.data.get('permissions') or [])
        wanted = {
            p.id: p.code for p in Permission.objects.all() if p.code in codes
        }
        with transaction.atomic():
            role.role_permissions.all().delete()
            RolePermission.objects.bulk_create(
                [RolePermission(role=role, permission_id=pid) for pid in wanted]
            )
        ServiceAuditLog.log(
            'rbac.role_permissions_set', request=request,
            object_type='role', object_id=str(role.id),
            metadata={'permissions': sorted(wanted.values())},
        )
        return Response({'permissions': sorted(wanted.values())})


class UserRoleViewSet(viewsets.ModelViewSet):
    """B2.5 — assign / revoke roles for users within a company."""
    serializer_class = UserRoleSerializer
    permission_classes = [HasRBACPermission]
    required_permissions = {'default': 'roles.manage', 'list': 'roles.manage'}

    def get_queryset(self):
        qs = UserRole.objects.select_related('role')
        org_id = self.request.query_params.get('organization')
        if org_id:
            qs = qs.filter(organization_id=org_id)
        user_id = self.request.query_params.get('user_id')
        if user_id:
            qs = qs.filter(user_id=user_id)
        return qs

    def perform_create(self, serializer):
        ur = serializer.save()
        ServiceAuditLog.log(
            'rbac.role_assigned', request=self.request,
            object_type='user_role', object_id=str(ur.id),
            metadata={'user_id': str(ur.user_id), 'role': ur.role.name,
                      'organization_id': str(ur.organization_id)},
        )

    def perform_destroy(self, instance):
        ServiceAuditLog.log(
            'rbac.role_revoked', request=self.request,
            object_type='user_role', object_id=str(instance.id),
            metadata={'user_id': str(instance.user_id), 'role': instance.role.name},
        )
        instance.delete()


class OrganigramNodeViewSet(viewsets.ModelViewSet):
    """B2.4 — per-company org chart nodes."""
    serializer_class = OrganigramNodeSerializer
    permission_classes = [HasRBACPermission]
    required_permissions = {'default': 'organization.manage',
                            'list': 'organization.manage',
                            'retrieve': 'organization.manage'}

    def get_queryset(self):
        qs = OrganigramNode.objects.select_related('role')
        org_id = self.request.query_params.get('organization')
        if org_id:
            qs = qs.filter(organization_id=org_id)
        return qs
