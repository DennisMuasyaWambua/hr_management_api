"""
drf-spectacular extensions: documents ServiceKeyAuthentication as an apiKey
security scheme so Swagger UI offers an "Authorize" box for X-Service-Key.
"""
from drf_spectacular.extensions import OpenApiAuthenticationExtension


class ServiceKeyAuthScheme(OpenApiAuthenticationExtension):
    target_class = 'apps.payroll.authentication.ServiceKeyAuthentication'
    name = 'ServiceKeyAuth'

    def get_security_definition(self, auto_schema):
        return {
            'type': 'apiKey',
            'in': 'header',
            'name': 'X-Service-Key',
            'description': (
                'Service-to-service key used by the Next.js apps. Pair with the '
                'identity headers X-User-Id / X-User-Role / X-User-Email / '
                'X-Company-Id for RBAC enforcement.'
            ),
        }
