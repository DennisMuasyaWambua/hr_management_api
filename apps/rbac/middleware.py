"""
Part B1 — RBAC middleware.

Resolves the requesting user's active Organization and permission set once per
request and attaches them to the request object so views, the permission class,
and audit logging can all read a consistent answer:

    request.rbac_organization   -> Organization | None
    request.rbac_permissions     -> set[str]   (e.g. {'payroll.view', ...})

This is intentionally cheap and never raises: missing identity simply yields an
empty permission set. Actual allow/deny happens in HasRBACPermission so that
DRF can return a clean 403 with a message.
"""
from .permissions import resolve_organization, resolve_permissions, request_user_id


class RBACContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            org = resolve_organization(request)
            request.rbac_organization = org
            request._rbac_permissions = resolve_permissions(
                request_user_id(request), org)
        except Exception:
            request.rbac_organization = None
            request._rbac_permissions = set()
        return self.get_response(request)
