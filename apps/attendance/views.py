"""
Attendance API: face check-in/out, location pings (spatio-temporal log),
work-zone management, HQ geofence dashboard, attendance rates.

Visibility rule (01-Jun session): geofence flags are HQ-dashboard only —
the PWA never receives other employees' zone status, and an employee's own
check-in response includes only what they need (whether a reason is required).
"""
from django.db.models import Count, Q
from django.utils import timezone
from drf_spectacular.utils import (OpenApiParameter, OpenApiResponse,
                                   extend_schema, inline_serializer)
from rest_framework import serializers as drf_serializers
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.models import ServiceAuditLog
from apps.core.permissions import (HasModulePermission, request_company_id,
                                   request_user_id)

from .models import (AttendanceEvent, EmployeeZoneAssignment, GeofenceViolation,
                     WorkZone, haversine_m)
from .serializers import (AttendanceEventSerializer, CheckInSerializer,
                          GeofenceViolationSerializer, WorkZoneSerializer,
                          ZoneAssignmentSerializer)
from .services import smileid


class WorkZoneViewSet(viewsets.ModelViewSet):
    serializer_class = WorkZoneSerializer
    permission_classes = [HasModulePermission]
    rbac_module = 'geofence'

    def get_queryset(self):
        qs = WorkZone.objects.all()
        company_id = request_company_id(self.request)
        if company_id:
            qs = qs.filter(company_id=company_id)
        return qs

    @action(detail=True, methods=['post'])
    def assign(self, request, pk=None):
        """Assign employees to this zone. Body: {"employee_ids": [...]}"""
        zone = self.get_object()
        created = []
        for emp_id in request.data.get('employee_ids', []):
            obj, was_created = EmployeeZoneAssignment.objects.get_or_create(
                employee_id=emp_id, zone=zone,
                defaults={'company_id': zone.company_id})
            if was_created:
                created.append(str(emp_id))
        return Response({'assigned': created})


class CheckInView(APIView):
    """
    PWA check-in/out with optional selfie (Smile ID) and GPS.
    Writes an AttendanceEvent to the Timescale hypertable, evaluates the
    geofence, and opens a GeofenceViolation when out of zone in work hours.
    """
    @extend_schema(
        summary='Face + GPS check-in/out (PWA)',
        description='Verifies the selfie via Smile ID (when provided), logs a '
                    'spatio-temporal AttendanceEvent, evaluates the assigned '
                    'work-zone geofence and flags out-of-zone episodes. The '
                    'response only exposes the caller\'s own status — never '
                    'other employees\' locations.',
        request=CheckInSerializer,
        responses={
            201: inline_serializer('CheckInResult', {
                'ok': drf_serializers.BooleanField(),
                'event_id': drf_serializers.IntegerField(),
                'event_type': drf_serializers.CharField(),
                'face_verified': drf_serializers.BooleanField(allow_null=True),
                'reason_required': drf_serializers.BooleanField(),
            }),
            403: OpenApiResponse(description='Face not recognized'),
            502: OpenApiResponse(description='Smile ID unreachable'),
        },
    )
    def post(self, request):
        ser = CheckInSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data

        face_result = {'verified': None, 'confidence': None}
        if d.get('selfie_b64'):
            try:
                face_result = smileid.verify_selfie(str(d['employee_id']),
                                                    d['selfie_b64'])
            except smileid.SmileIDError as exc:
                return Response({'error': f'Face verification failed: {exc}'},
                                status=status.HTTP_502_BAD_GATEWAY)
            if not face_result['verified']:
                ServiceAuditLog.log('attendance.face_rejected', request=request,
                                    object_type='employee',
                                    object_id=str(d['employee_id']),
                                    company_id=d.get('company_id'))
                return Response({'error': 'Face not recognized',
                                 'confidence': face_result['confidence']},
                                status=status.HTTP_403_FORBIDDEN)

        zone, in_zone, distance = self._evaluate_zone(d)
        event = AttendanceEvent.objects.create(
            company_id=d['company_id'], employee_id=d['employee_id'],
            tenant_id=d.get('tenant_id'),
            event_type=d['event_type'], lat=d.get('lat'), lng=d.get('lng'),
            accuracy_m=d.get('accuracy_m'),
            zone_id=zone.id if zone else None, in_zone=in_zone,
            face_verified=face_result['verified'],
            face_confidence=face_result['confidence'],
            device_id=d.get('device_id', ''),
            out_of_zone_reason=d.get('out_of_zone_reason', ''),
        )

        reason_required = False
        if in_zone is False and self._in_work_hours(zone):
            reason_required = not d.get('out_of_zone_reason')
            violation = GeofenceViolation.objects.filter(
                employee_id=d['employee_id'], ended_at__isnull=True).first()
            if violation is None:
                GeofenceViolation.objects.create(
                    company_id=d['company_id'], employee_id=d['employee_id'],
                    tenant_id=d.get('tenant_id'), zone=zone,
                    started_at=timezone.now(), distance_m=distance,
                    reason=d.get('out_of_zone_reason', ''),
                    status='reason_submitted' if d.get('out_of_zone_reason') else 'open')
        elif in_zone:
            GeofenceViolation.objects.filter(
                employee_id=d['employee_id'], ended_at__isnull=True,
            ).update(ended_at=timezone.now())

        # Employee-facing response: own status only, no other staff data.
        return Response({
            'ok': True, 'event_id': event.id, 'event_type': event.event_type,
            'face_verified': face_result['verified'],
            'reason_required': reason_required,
        }, status=status.HTTP_201_CREATED)

    @staticmethod
    def _evaluate_zone(d):
        if d.get('lat') is None or d.get('lng') is None:
            return None, None, None
        assignment = EmployeeZoneAssignment.objects.filter(
            employee_id=d['employee_id'], is_active=True,
            zone__is_active=True).select_related('zone').first()
        if assignment is None:
            return None, None, None
        zone = assignment.zone
        distance = haversine_m(zone.center_lat, zone.center_lng,
                               d['lat'], d['lng'])
        return zone, distance <= zone.radius_m, distance

    @staticmethod
    def _in_work_hours(zone):
        if zone is None:
            return True
        now = timezone.localtime().time()
        return zone.work_start <= now <= zone.work_end


class LocationPingView(APIView):
    """Lightweight periodic GPS ping from the PWA → hypertable row."""
    @extend_schema(
        summary='Background GPS ping (PWA)',
        request=CheckInSerializer,
        responses={201: inline_serializer('PingResult', {
            'ok': drf_serializers.BooleanField(),
            'event_id': drf_serializers.IntegerField(),
        })},
    )
    def post(self, request):
        d = request.data
        required = ('employee_id', 'company_id', 'lat', 'lng')
        if any(d.get(k) is None for k in required):
            return Response({'error': f'required: {required}'},
                            status=status.HTTP_400_BAD_REQUEST)
        ser = CheckInSerializer(data={**d, 'event_type': 'location_ping'})
        ser.is_valid(raise_exception=True)
        view = CheckInView()
        zone, in_zone, distance = view._evaluate_zone(ser.validated_data)
        event = AttendanceEvent.objects.create(
            company_id=d['company_id'], employee_id=d['employee_id'],
            tenant_id=d.get('tenant_id'), event_type='location_ping',
            lat=d['lat'], lng=d['lng'], accuracy_m=d.get('accuracy_m'),
            zone_id=zone.id if zone else None, in_zone=in_zone,
            device_id=d.get('device_id', ''))
        return Response({'ok': True, 'event_id': event.id},
                        status=status.HTTP_201_CREATED)


class GeofenceDashboardView(APIView):
    """
    HQ dashboard: color-coded zone status per employee (green = in zone,
    red = out of zone, grey = no signal today). HR/admin only.
    """
    permission_classes = [HasModulePermission]
    rbac_module = 'geofence'

    @extend_schema(
        summary='HQ geofence dashboard (color-coded, HR/admin only)',
        parameters=[OpenApiParameter('company_id', str, required=True)],
        responses={200: OpenApiResponse(
            description='{"employees": [{employee_id, color: green|red|grey, '
                        'last_seen, event_type, lat, lng, in_zone, reason}], '
                        '"open_violations": [...]}')},
    )
    def get(self, request):
        company_id = request_company_id(request)
        if not company_id:
            return Response({'error': 'company_id required'},
                            status=status.HTTP_400_BAD_REQUEST)
        since = timezone.now() - timezone.timedelta(hours=12)
        latest = {}
        events = AttendanceEvent.objects.filter(
            company_id=company_id, time__gte=since).order_by('employee_id', '-time')
        for e in events:
            latest.setdefault(str(e.employee_id), e)
        rows = []
        for emp_id, e in latest.items():
            color = 'grey'
            if e.in_zone is True:
                color = 'green'
            elif e.in_zone is False:
                color = 'red'
            rows.append({'employee_id': emp_id, 'color': color,
                         'last_seen': e.time, 'event_type': e.event_type,
                         'lat': e.lat, 'lng': e.lng, 'in_zone': e.in_zone,
                         'reason': e.out_of_zone_reason})
        open_violations = GeofenceViolationSerializer(
            GeofenceViolation.objects.filter(company_id=company_id,
                                             ended_at__isnull=True), many=True).data
        return Response({'employees': rows, 'open_violations': open_violations})


class GeofenceViolationViewSet(viewsets.ModelViewSet):
    serializer_class = GeofenceViolationSerializer
    permission_classes = [HasModulePermission]
    rbac_module = 'geofence'
    http_method_names = ['get', 'patch', 'post', 'head', 'options']

    def get_queryset(self):
        qs = GeofenceViolation.objects.all()
        company_id = request_company_id(self.request)
        if company_id:
            qs = qs.filter(company_id=company_id)
        return qs

    @action(detail=True, methods=['post'])
    def submit_reason(self, request, pk=None):
        """Employee submits why they are outside their assigned zone."""
        v = self.get_object()
        v.reason = request.data.get('reason', '')
        v.status = 'reason_submitted'
        v.save(update_fields=['reason', 'status', 'updated_at'])
        return Response(self.get_serializer(v).data)


class AttendanceRateView(APIView):
    """Attendance rate for a company on a date (drives the <30% alert)."""
    permission_classes = [HasModulePermission]
    rbac_module = 'attendance'

    @extend_schema(
        summary='Attendance rate for a company on a date',
        parameters=[OpenApiParameter('company_id', str, required=True),
                    OpenApiParameter('date', str, description='ISO date; defaults to today')],
        responses={200: inline_serializer('AttendanceRate', {
            'date': drf_serializers.DateField(),
            'headcount': drf_serializers.IntegerField(),
            'checked_in': drf_serializers.IntegerField(),
            'rate': drf_serializers.FloatField(),
        })},
    )
    def get(self, request):
        from apps.payroll.models import EmployeeProfile
        company_id = request_company_id(request)
        date_str = request.query_params.get('date')
        day = timezone.datetime.fromisoformat(date_str).date() if date_str \
            else timezone.localdate()
        headcount = EmployeeProfile.objects.filter(
            company_id=company_id, employment_status='active',
            is_deleted=False).count()
        checked_in = AttendanceEvent.objects.filter(
            company_id=company_id, event_type='check_in',
            time__date=day).values('employee_id').distinct().count()
        rate = round(100 * checked_in / headcount, 1) if headcount else 0.0
        return Response({'date': str(day), 'headcount': headcount,
                         'checked_in': checked_in, 'rate': rate})


class AttendanceEventViewSet(viewsets.ReadOnlyModelViewSet):
    """HQ query access to the raw spatio-temporal log."""
    serializer_class = AttendanceEventSerializer
    permission_classes = [HasModulePermission]
    rbac_module = 'attendance'

    def get_queryset(self):
        qs = AttendanceEvent.objects.all()
        p = self.request.query_params
        company_id = request_company_id(self.request)
        if company_id:
            qs = qs.filter(company_id=company_id)
        if p.get('employee_id'):
            qs = qs.filter(employee_id=p['employee_id'])
        if p.get('from'):
            qs = qs.filter(time__gte=p['from'])
        if p.get('to'):
            qs = qs.filter(time__lte=p['to'])
        if p.get('event_type'):
            qs = qs.filter(event_type=p['event_type'])
        return qs
