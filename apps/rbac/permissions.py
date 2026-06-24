"""
Part B1 — permission enforcement for the B0 RBAC model.

Resolution order for a request:
  1. Identity comes from the forwarded headers (X-User-Id, X-Company-Id) that
     the dashboard/PWA proxies already stamp from the session.
  2. The active Organization is resolved from X-Organization-Id, or from
     X-Company-Id via the Organization.company_id bridge.
  3. The user's permission set = union of RolePermission codes for every Role
     granted to that user (via UserRole). A user holding the ``super_admin``
     role is granted every permission.

Enforcement is opt-in per view via ``HasRBACPermission`` + a
``required_permissions`` map, and globally gated by ``RBAC_ENFORCE`` (default
False) so legacy routes are never broken until they declare requirements.
"""
from django.conf import settings
from rest_framework.permissions import BasePermission

from .models import Organization, UserRole


def request_user_id(request):
    return request.headers.get('X-User-Id') or None


def resolve_organization(request):
    """Best-effort Organization for the request."""
    org_id = request.headers.get('X-Organization-Id')
    if org_id:
        return Organization.objects.filter(id=org_id).first()
    company_id = (
        request.headers.get('X-Company-Id')
        or request.headers.get('X-Company-ID')
    )
    if company_id:
        return Organization.objects.filter(company_id=company_id).first()
    return None


def resolve_permissions(user_id, organization=None):
    """Return the set of ``resource.action`` codes a user holds.

    If ``organization`` is given, only roles granted within that organization
    (plus system-role grants) are considered; otherwise all of the user's
    grants across every organization are unioned.
    """
    if not user_id:
        return set()

    qs = UserRole.objects.filter(user_id=user_id)
    if organization is not None:
        qs = qs.filter(organization=organization)
    role_ids = list(qs.values_list('role_id', flat=True))
    if not role_ids:
        return set()

    # super_admin short-circuit: every permission.
    from .models import Permission, Role
    if Role.objects.filter(id__in=role_ids, name='super_admin').exists():
        return {p.code for p in Permission.objects.all()}

    from .models import RolePermission
    codes = (
        RolePermission.objects
        .filter(role_id__in=role_ids)
        .select_related('permission')
    )
    return {rp.permission.code for rp in codes}


def user_permissions(request):
    """Resolve (and cache on the request) the caller's permission set."""
    cached = getattr(request, '_rbac_permissions', None)
    if cached is not None:
        return cached
    org = getattr(request, 'rbac_organization', None)
    if org is None:
        org = resolve_organization(request)
        request.rbac_organization = org
    perms = resolve_permissions(request_user_id(request), org)
    request._rbac_permissions = perms
    return perms


def rbac_enforced():
    return bool(getattr(settings, 'RBAC_ENFORCE', False))


class HasRBACPermission(BasePermission):
    """Enforce a per-action permission requirement declared on the view.

    Usage on a ViewSet::

        class FooViewSet(viewsets.ModelViewSet):
            permission_classes = [HasRBACPermission]
            required_permissions = {
                'list': 'report.view', 'create': 'report.export',
                'default': 'report.view',
            }

    A view may instead set a single string ``required_permission``. When
    ``RBAC_ENFORCE`` is False the class still resolves perms (so views can read
    them) but never denies — keeping legacy behavior intact.
    """
    message = 'You do not have permission to perform this action.'

    def _required(self, request, view):
        single = getattr(view, 'required_permission', None)
        if single:
            return single
        mapping = getattr(view, 'required_permissions', None) or {}
        action = getattr(view, 'action', None) or request.method.lower()
        return mapping.get(action) or mapping.get('default')

    def has_permission(self, request, view):
        required = self._required(request, view)
        if not required:
            return True
        perms = user_permissions(request)
        allowed = required in perms
        if not allowed and not rbac_enforced():
            # Soft mode: don't break legacy callers, but make the gap visible.
            try:
                from apps.core.models import ServiceAuditLog
                ServiceAuditLog.log(
                    'rbac.permission_soft_deny', request=request,
                    object_type='permission', object_id=required,
                    metadata={'required': required},
                )
            except Exception:
                pass
            return True
        return allowed


class IsSuperAdmin(BasePermission):
    """Only a user holding the super_admin role (any org)."""
    message = 'Super admin access required.'

    def has_permission(self, request, view):
        uid = request_user_id(request)
        if not uid:
            return not rbac_enforced()
        from .models import Role, UserRole as _UR
        is_sa = _UR.objects.filter(
            user_id=uid, role__name='super_admin').exists()
        return is_sa or not rbac_enforced()
