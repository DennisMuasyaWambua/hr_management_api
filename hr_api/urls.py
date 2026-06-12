"""
URL configuration for HR-API project.
"""

from django.contrib import admin
from django.urls import path, include
from rest_framework.authtoken.views import obtain_auth_token

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/token/', obtain_auth_token, name='api_token_auth'),
    path('', include('apps.payroll.urls')),
    path('api/', include('apps.core.urls')),
    path('api/', include('apps.hr.urls')),
    path('api/', include('apps.attendance.urls')),
]
