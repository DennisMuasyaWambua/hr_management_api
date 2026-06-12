from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (AttendanceEventViewSet, AttendanceRateView, CheckInView,
                    GeofenceDashboardView, GeofenceViolationViewSet,
                    LocationPingView, WorkZoneViewSet)

router = DefaultRouter()
router.register('work-zones', WorkZoneViewSet, basename='work-zones')
router.register('geofence-violations', GeofenceViolationViewSet,
                basename='geofence-violations')
router.register('attendance-events', AttendanceEventViewSet,
                basename='attendance-events')

urlpatterns = router.urls + [
    path('attendance/check-in/', CheckInView.as_view(), name='attendance-check-in'),
    path('attendance/ping/', LocationPingView.as_view(), name='attendance-ping'),
    path('attendance/rate/', AttendanceRateView.as_view(), name='attendance-rate'),
    path('geofence/dashboard/', GeofenceDashboardView.as_view(),
         name='geofence-dashboard'),
]
