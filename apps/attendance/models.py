"""
Attendance & geofencing models.

AttendanceEvent is the spatio-temporal log from the PWA. On PostgreSQL with
the timescaledb extension it becomes a hypertable partitioned on `time`
(see migration 0002_timescale_hypertable); on SQLite/plain Postgres it is a
regular table, so dev keeps working unchanged.

Routing: when TIMESCALE_ENABLED and a 'timescale' DB alias is configured,
apps.attendance models live in that database (see apps.attendance.router).
"""
import math
import uuid

from django.db import models
from django.utils import timezone


class WorkZone(models.Model):
    """Geofenced work area: circle (center + radius). HQ-dashboard managed."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    tenant_id = models.UUIDField(null=True, blank=True, db_index=True)
    company_id = models.UUIDField(db_index=True)
    name = models.CharField(max_length=255)
    center_lat = models.FloatField()
    center_lng = models.FloatField()
    radius_m = models.PositiveIntegerField(default=200)
    work_start = models.TimeField(default='08:00')
    work_end = models.TimeField(default='17:00')
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'work_zones'

    def __str__(self):
        return f'{self.name} ({self.radius_m}m)'

    def contains(self, lat: float, lng: float) -> bool:
        return haversine_m(self.center_lat, self.center_lng, lat, lng) <= self.radius_m


class EmployeeZoneAssignment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    employee_id = models.UUIDField(db_index=True)
    company_id = models.UUIDField(db_index=True)
    zone = models.ForeignKey(WorkZone, on_delete=models.CASCADE,
                             related_name='assignments')
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'employee_zone_assignments'
        unique_together = [('employee_id', 'zone')]


class AttendanceEvent(models.Model):
    """Spatio-temporal event log (Timescale hypertable on `time`)."""
    EVENT_TYPES = [('check_in', 'Check in'), ('check_out', 'Check out'),
                   ('location_ping', 'Location ping'),
                   ('geofence_exit', 'Geofence exit'),
                   ('geofence_enter', 'Geofence enter')]

    # NOTE: hypertables need `time` in the PK; migration 0002 swaps the PK to
    # (id, time) on Timescale-enabled Postgres.
    id = models.BigAutoField(primary_key=True)
    time = models.DateTimeField(default=timezone.now, db_index=True)
    tenant_id = models.UUIDField(null=True, blank=True, db_index=True)
    company_id = models.UUIDField(db_index=True)
    employee_id = models.UUIDField(db_index=True)
    event_type = models.CharField(max_length=20, choices=EVENT_TYPES)
    lat = models.FloatField(null=True, blank=True)
    lng = models.FloatField(null=True, blank=True)
    accuracy_m = models.FloatField(null=True, blank=True)
    zone_id = models.UUIDField(null=True, blank=True)
    in_zone = models.BooleanField(null=True)
    face_verified = models.BooleanField(null=True)
    face_confidence = models.FloatField(null=True, blank=True)
    device_id = models.CharField(max_length=255, blank=True, default='')
    out_of_zone_reason = models.TextField(blank=True, default='')
    source_app = models.CharField(max_length=20, default='pwa')

    class Meta:
        db_table = 'attendance_events'
        ordering = ['-time']
        indexes = [
            models.Index(fields=['company_id', 'time']),
            models.Index(fields=['employee_id', 'time']),
        ]


class GeofenceViolation(models.Model):
    """Out-of-zone episode during work hours. HQ-dashboard visible ONLY."""
    STATUS = [('open', 'Open'), ('reason_submitted', 'Reason submitted'),
              ('reviewed', 'Reviewed')]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    tenant_id = models.UUIDField(null=True, blank=True, db_index=True)
    company_id = models.UUIDField(db_index=True)
    employee_id = models.UUIDField(db_index=True)
    zone = models.ForeignKey(WorkZone, null=True, blank=True,
                             on_delete=models.SET_NULL)
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True, blank=True)
    distance_m = models.FloatField(null=True, blank=True)
    reason = models.TextField(blank=True, default='')
    status = models.CharField(max_length=20, choices=STATUS, default='open')
    reviewed_by = models.UUIDField(null=True, blank=True)

    class Meta:
        db_table = 'geofence_violations'
        ordering = ['-started_at']


def haversine_m(lat1, lng1, lat2, lng2) -> float:
    """Great-circle distance in meters."""
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))
