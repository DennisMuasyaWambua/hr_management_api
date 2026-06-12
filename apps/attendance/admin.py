from django.contrib import admin

from .models import (AttendanceEvent, EmployeeZoneAssignment,
                     GeofenceViolation, WorkZone)

admin.site.register(WorkZone)
admin.site.register(EmployeeZoneAssignment)


@admin.register(AttendanceEvent)
class AttendanceEventAdmin(admin.ModelAdmin):
    list_display = ('time', 'employee_id', 'event_type', 'in_zone', 'face_verified')
    list_filter = ('event_type', 'in_zone')


admin.site.register(GeofenceViolation)
