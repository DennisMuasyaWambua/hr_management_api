"""
Custom authentication for internal service-to-service calls.
"""
import hmac

from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from django.conf import settings
from django.contrib.auth import get_user_model

User = get_user_model()


class ServiceUser:
    """
    A mock user object for service-to-service authentication.
    """
    def __init__(self):
        self.id = 0
        self.pk = 0
        self.username = 'hr_dashboard_service'
        self.is_authenticated = True
        self.is_active = True
        self.is_staff = True
        self.tenant_id = None  # Will be set per-request if company_id provided
        self.company_id = None

    def __str__(self):
        return self.username


class ServiceKeyAuthentication(BaseAuthentication):
    """
    Simple service key authentication for internal API calls.

    Usage:
    - Set HR_SERVICE_KEY in Django settings/environment
    - Send header: X-Service-Key: your_service_key
    """

    def authenticate(self, request):
        service_key = getattr(settings, 'HR_SERVICE_KEY', None)

        if not service_key:
            return None  # No service key configured, skip this auth method

        # Check for service key header
        provided_key = request.headers.get('X-Service-Key')

        if not provided_key:
            return None  # No key provided, let other auth methods handle it

        if not hmac.compare_digest(provided_key, service_key):
            raise AuthenticationFailed('Invalid service key')

        # Create a service user
        user = ServiceUser()

        # If company_id is provided in request, set it on the user
        company_id = (
            request.data.get('company_id') or
            request.query_params.get('company_id') or
            request.query_params.get('companyId')
        )
        if company_id:
            user.tenant_id = company_id
            user.company_id = company_id

        return (user, None)

    def authenticate_header(self, request):
        return 'X-Service-Key'
