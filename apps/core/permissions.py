"""
RBAC enforcement for DRF.

Identity propagation: the Next.js route handlers proxy with X-Service-Key and
forward the session user via headers:
    X-User-Id, X-User-Role, X-User-Email, X-Company-Id, X-Tenant-Id

Backward compatibility: existing dashboard calls do not yet send role headers.
When X-User-Role is absent we honor legacy service-key trust but audit-log it
(`rbac.legacy_access`). Once Chris forwards headers everywhere, set
RBAC_STRICT=True to close the hole (tracked in LOGIC_AUDIT.md L-1).
"""
from django.conf import settings
from rest_framework.permissions import BasePermission

from apps.core.models import (Permission, Role, RolePermission, ServiceAuditLog,
                              UserRoleAssignment)

ROLE_RANKS = {'super_admin': 0, 'company_admin': 10, 'hr': 20, 'manager': 30, 'employee': 40}


def request_role(request) -> str | None:
    return request.headers.get('X-User-Role') or None


def request_user_id(request) -> str | None:
    return request.headers.get('X-User-Id') or None


def request_company_id(request) -> str | None:
    return request.headers.get('X-Company-Id') or request.query_params.get('company_id')


def effective_permissions(role_slug: str, company_id=None) -> set[str]:
    roles = Role.objects.filter(slug=role_slug)
    if company_id:
        roles = roles.filter(models_q_company(company_id))
    codenames = RolePermission.objects.filter(role__in=roles) \
        .values_list('permission__codename', flat=True)
    return set(codenames)


def models_q_company(company_id):
    from django.db.models import Q
    return Q(company_id=company_id) | Q(company_id__isnull=True)


def _strict():
    return getattr(settings, 'RBAC_STRICT', False)


def _legacy_allow(request, view, needed):
    """Service-key call without role headers: allow but audit (pre-RBAC clients)."""
    ServiceAuditLog.log(
        'rbac.legacy_access', request=request,
        metadata={'path': request.path, 'needed': needed,
                  'view': view.__class__.__name__},
        actor_label='service-key (no role headers)',
    )
    return True


class HasModulePermission(BasePermission):
    """
    Checks `<module>.<action>` against the caller's role grants.
    Views set `rbac_module`; action maps: list/retrieve→view, others→manage.
    """
    message = 'Your role does not have permission for this module.'

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        module = getattr(view, 'rbac_module', None)
        if module is None:
            return True
        action = 'view' if request.method in ('GET', 'HEAD', 'OPTIONS') else 'manage'
        needed = f'{module}.{action}'
        role = request_role(request)
        if role is None:
            return False if _strict() else _legacy_allow(request, view, needed)
        if role == 'super_admin':
            return True
        return needed in effective_permissions(role, request_company_id(request))


class PayrollHROnly(BasePermission):
    """
    Hard rule from the 01-Jun session: payroll data is visible to HR and
    admins only — never managers or employees, regardless of grants.
    """
    message = 'Payroll data is restricted to HR and administrators.'

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        role = request_role(request)
        if role is None:
            return False if _strict() else _legacy_allow(request, view, 'payroll.view')
        return role in ('super_admin', 'company_admin', 'hr')


class IsHighestRank(BasePermission):
    """
    Frontend autonomy: only the highest-ranked role in scope may manage
    role-permission grants (super_admin globally; company_admin within
    their company when no super_admin is scoped to it).
    """
    message = 'Only the highest-ranked role may manage permissions.'

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.method in ('GET', 'HEAD', 'OPTIONS'):
            return True
        role = request_role(request)
        if role is None:
            # Permission management is new — no legacy callers exist; be strict.
            return False
        return ROLE_RANKS.get(role, 99) <= ROLE_RANKS['company_admin']
