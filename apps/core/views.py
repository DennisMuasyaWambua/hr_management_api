"""
Core API: RBAC management (frontend autonomy), notifications, one-tap
approvals, audit log access.
"""
from django.utils import timezone
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (AppUser, NotificationLog, NotificationTemplate,
                     OneTapToken, Permission, Role, RolePermission,
                     ServiceAuditLog, UserRoleAssignment)
from .permissions import (HasModulePermission, IsHighestRank,
                          request_company_id, request_user_id)
from .serializers import (AppUserSerializer, NotificationLogSerializer,
                          NotificationTemplateSerializer, PermissionSerializer,
                          RolePermissionSerializer, RoleSerializer,
                          SendNotificationSerializer,
                          ServiceAuditLogSerializer,
                          UserRoleAssignmentSerializer)
from .services import notifications as notif


def _scope_company(qs, request):
    company_id = request_company_id(request)
    if company_id:
        from django.db.models import Q
        return qs.filter(Q(company_id=company_id) | Q(company_id__isnull=True))
    return qs


class AppUserViewSet(viewsets.ModelViewSet):
    """User directory (HR admins, managers, employees) — replaces direct
    Supabase queries against the old `users` table. Only role/is_active are
    editable from the dashboard; identity fields are managed by login."""
    serializer_class = AppUserSerializer
    permission_classes = [IsHighestRank]
    http_method_names = ['get', 'put', 'patch', 'head', 'options']

    def get_queryset(self):
        qs = AppUser.objects.filter(is_deleted=False)
        company_id = (self.request.query_params.get('companyId') or
                     self.request.query_params.get('company_id'))
        if company_id:
            qs = qs.filter(company_id=company_id)
        return qs.order_by('full_name')


class RoleViewSet(viewsets.ModelViewSet):
    """Roles + their grants. Mutations restricted to the highest rank."""
    serializer_class = RoleSerializer
    permission_classes = [IsHighestRank]
    rbac_module = 'rbac'

    def get_queryset(self):
        return _scope_company(Role.objects.all().prefetch_related('grants__permission'),
                              self.request)

    @action(detail=True, methods=['post'])
    def grant(self, request, pk=None):
        """Grant permission codenames to this role. Body: {"codenames": [...]}"""
        role = self.get_object()
        codenames = request.data.get('codenames', [])
        granted = []
        for codename in codenames:
            try:
                perm = Permission.objects.get(codename=codename)
            except Permission.DoesNotExist:
                return Response({'error': f'Unknown permission: {codename}'},
                                status=status.HTTP_400_BAD_REQUEST)
            _, created = RolePermission.objects.get_or_create(
                role=role, permission=perm,
                defaults={'granted_by': request_user_id(request)})
            if created:
                granted.append(codename)
        ServiceAuditLog.log('rbac.grant', request=request,
                            object_type='role', object_id=str(role.id),
                            company_id=role.company_id,
                            metadata={'granted': granted, 'requested': codenames})
        return Response(RoleSerializer(role).data)

    @action(detail=True, methods=['post'])
    def revoke(self, request, pk=None):
        """Revoke permission codenames from this role. Body: {"codenames": [...]}"""
        role = self.get_object()
        codenames = request.data.get('codenames', [])
        deleted, _ = RolePermission.objects.filter(
            role=role, permission__codename__in=codenames).delete()
        ServiceAuditLog.log('rbac.revoke', request=request,
                            object_type='role', object_id=str(role.id),
                            company_id=role.company_id,
                            metadata={'revoked': codenames, 'count': deleted})
        return Response(RoleSerializer(role).data)


class PermissionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Permission.objects.all()
    serializer_class = PermissionSerializer
    rbac_module = 'rbac'
    permission_classes = [HasModulePermission]
    pagination_class = None


class UserRoleAssignmentViewSet(viewsets.ModelViewSet):
    serializer_class = UserRoleAssignmentSerializer
    permission_classes = [IsHighestRank]
    rbac_module = 'rbac'

    def get_queryset(self):
        qs = UserRoleAssignment.objects.select_related('role')
        company_id = request_company_id(self.request)
        if company_id:
            qs = qs.filter(company_id=company_id)
        user_id = self.request.query_params.get('user_id')
        if user_id:
            qs = qs.filter(user_id=user_id)
        return qs

    def perform_create(self, serializer):
        instance = serializer.save(assigned_by=request_user_id(self.request))
        ServiceAuditLog.log('rbac.assign_role', request=self.request,
                            object_type='user', object_id=str(instance.user_id),
                            company_id=instance.company_id,
                            metadata={'role': instance.role.slug})

    def perform_destroy(self, instance):
        ServiceAuditLog.log('rbac.unassign_role', request=self.request,
                            object_type='user', object_id=str(instance.user_id),
                            company_id=instance.company_id,
                            metadata={'role': instance.role.slug})
        instance.delete()


class NotificationTemplateViewSet(viewsets.ModelViewSet):
    serializer_class = NotificationTemplateSerializer
    permission_classes = [HasModulePermission]
    rbac_module = 'notifications'

    def get_queryset(self):
        return _scope_company(NotificationTemplate.objects.all(), self.request)


class NotificationViewSet(viewsets.GenericViewSet):
    """Unified send + delivery log for all three frontends."""
    permission_classes = [HasModulePermission]
    rbac_module = 'notifications'
    queryset = NotificationLog.objects.all()
    serializer_class = NotificationLogSerializer

    @action(detail=False, methods=['post'])
    def send(self, request):
        ser = SendNotificationSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        if d['event']:
            log_ids = notif.notify(
                d['event'], d['recipients'], d['context'],
                channels=d['channels'], company_id=d.get('company_id'),
                source_app=d['source_app'])
        else:
            # Ad-hoc message (no template event)
            log_ids = []
            for channel in d['channels']:
                for r in d['recipients']:
                    addr = r.get('email') if channel == 'email' else r.get('phone')
                    if not addr:
                        continue
                    if channel == 'email':
                        log = notif.send_email(addr, d['subject'] or 'Notification',
                                               d['message'],
                                               company_id=d.get('company_id'),
                                               source_app=d['source_app'])
                    else:
                        log = notif.SENDERS[channel](addr, d['message'],
                                                     company_id=d.get('company_id'),
                                                     source_app=d['source_app'])
                    log_ids.append(str(log.id))
        return Response({'queued': log_ids}, status=status.HTTP_202_ACCEPTED)

    @action(detail=False, methods=['get'])
    def logs(self, request):
        qs = self.get_queryset()
        company_id = request_company_id(request)
        if company_id:
            qs = qs.filter(company_id=company_id)
        page = self.paginate_queryset(qs)
        return self.get_paginated_response(
            NotificationLogSerializer(page, many=True).data)


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ServiceAuditLogSerializer
    permission_classes = [HasModulePermission]
    rbac_module = 'audit'

    def get_queryset(self):
        qs = ServiceAuditLog.objects.all()
        company_id = request_company_id(self.request)
        if company_id:
            qs = qs.filter(company_id=company_id)
        action_filter = self.request.query_params.get('action')
        if action_filter:
            qs = qs.filter(action__startswith=action_filter)
        return qs


class OneTapApprovalView(APIView):
    """
    Tokenized one-tap approval target for links sent over SMS/WhatsApp/email.
    GET returns what would be approved; POST executes. No session required —
    possession of the unexpired single-use token is the credential.
    """
    authentication_classes = []  # token IS the auth
    permission_classes = []

    def _get_token(self, token):
        try:
            return OneTapToken.objects.get(token=token)
        except OneTapToken.DoesNotExist:
            return None

    @extend_schema(
        summary='Inspect a one-tap approval token',
        request=None,
        responses={200: OpenApiResponse(description='{"valid", "action", "object_id", "expires_at"}'),
                   404: OpenApiResponse(description='Token invalid, used or expired')},
    )
    def get(self, request, token):
        t = self._get_token(token)
        if t is None or not t.is_valid:
            return Response({'valid': False, 'error': 'Token invalid, used or expired'},
                            status=status.HTTP_404_NOT_FOUND)
        return Response({'valid': True, 'action': t.action, 'object_id': t.object_id,
                         'expires_at': t.expires_at})

    @extend_schema(
        summary='Execute a one-tap approval (single use)',
        description='The unexpired single-use token IS the credential — links '
                    'are sent to approvers over SMS/WhatsApp/email. Executes '
                    'exactly one predefined action (approve/reject overtime, '
                    'leave recall or payroll run) and burns the token.',
        request=None,
        responses={200: OpenApiResponse(description='{"ok", "action", "result"}'),
                   404: OpenApiResponse(description='Token invalid, used or expired')},
    )
    def post(self, request, token):
        t = self._get_token(token)
        if t is None or not t.is_valid:
            return Response({'error': 'Token invalid, used or expired'},
                            status=status.HTTP_404_NOT_FOUND)
        from apps.core.approval_actions import execute_one_tap_action
        result = execute_one_tap_action(t, request)
        t.used_at = timezone.now()
        t.save(update_fields=['used_at'])
        ServiceAuditLog.log(f'one_tap.{t.action}', request=request,
                            object_type=t.action.split('.')[0], object_id=t.object_id,
                            company_id=t.company_id,
                            actor_user_id=t.approver_user_id,
                            metadata={'result': result})
        return Response({'ok': True, 'action': t.action, 'result': result})
