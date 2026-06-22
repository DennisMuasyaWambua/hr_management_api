from rest_framework import serializers

from .models import (AttendanceEvent, EmployeeZoneAssignment,
                     GeofenceViolation, WorkZone)


class WorkZoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkZone
        fields = '__all__'


class ZoneAssignmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmployeeZoneAssignment
        fields = '__all__'


class AttendanceEventSerializer(serializers.ModelSerializer):
    employee_name = serializers.SerializerMethodField()

    def get_employee_name(self, obj):
        return getattr(obj, 'employee_name', None)

    class Meta:
        model = AttendanceEvent
        fields = '__all__'


class GeofenceViolationSerializer(serializers.ModelSerializer):
    class Meta:
        model = GeofenceViolation
        fields = '__all__'


class CheckInSerializer(serializers.Serializer):
    employee_id = serializers.UUIDField()
    company_id = serializers.UUIDField()
    tenant_id = serializers.UUIDField(required=False, allow_null=True)
    event_type = serializers.ChoiceField(
        choices=['check_in', 'check_out', 'location_ping'], default='check_in')
    lat = serializers.FloatField(required=False, allow_null=True)
    lng = serializers.FloatField(required=False, allow_null=True)
    accuracy_m = serializers.FloatField(required=False, allow_null=True)
    selfie_b64 = serializers.CharField(required=False, allow_blank=True)
    device_id = serializers.CharField(required=False, allow_blank=True, default='')
    out_of_zone_reason = serializers.CharField(required=False, allow_blank=True,
                                               default='')
