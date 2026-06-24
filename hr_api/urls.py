"""
URL configuration for HR-API project.
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.permissions import IsAuthenticated
from rest_framework.throttling import AnonRateThrottle
from drf_spectacular.views import (SpectacularAPIView, SpectacularRedocView,
                                   SpectacularSwaggerView)


class _LoginThrottle(AnonRateThrottle):
    scope = 'login'


class _ThrottledObtainAuthToken(ObtainAuthToken):
    throttle_classes = [_LoginThrottle]


ADMIN_URL = getattr(settings, 'ADMIN_URL', 'admin/')

urlpatterns = [
    path(ADMIN_URL, admin.site.urls),
    path('api/token/', _ThrottledObtainAuthToken.as_view(), name='api_token_auth'),
    path('', include('apps.payroll.urls')),
    path('api/', include('apps.core.urls')),
    path('api/', include('apps.hr.urls')),
    path('api/', include('apps.attendance.urls')),
    path('api/', include('apps.recruitment.urls')),
    path('api/', include('apps.actions.urls')),
    path('api/', include('apps.workflows.urls')),
    path('api/', include('apps.crm.urls')),
    path('api/', include('apps.matching.urls')),
    path('api/', include('apps.analytics.urls')),
    path('api/', include('apps.lms.urls')),
    path('api/', include('apps.performance.urls')),
    # OpenAPI / Swagger documentation (authenticated — not public)
    path('api/schema/', SpectacularAPIView.as_view(permission_classes=[IsAuthenticated]), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema', permission_classes=[IsAuthenticated]),
         name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema', permission_classes=[IsAuthenticated]),
         name='redoc'),
]
