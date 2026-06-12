"""
Attendance periodic tasks:
  - low_attendance_report: daily 10:00 — when a company's attendance is below
    threshold (default 30%), email the stakeholder a report (per 01-Jun notes).
"""
from celery import shared_task
from django.utils import timezone

LOW_ATTENDANCE_THRESHOLD = 30.0


@shared_task
def low_attendance_report(threshold: float = LOW_ATTENDANCE_THRESHOLD):
    from apps.attendance.models import AttendanceEvent
    from apps.core.services import notifications as notif
    from apps.payroll.models import Company, EmployeeProfile

    today = timezone.localdate()
    alerts = []
    for company in Company.objects.filter(is_active=True, is_deleted=False):
        headcount = EmployeeProfile.objects.filter(
            company_id=company.id, employment_status='active',
            is_deleted=False).count()
        if headcount == 0:
            continue
        checked_in = AttendanceEvent.objects.filter(
            company_id=company.id, event_type='check_in',
            time__date=today).values('employee_id').distinct().count()
        rate = round(100 * checked_in / headcount, 1)
        if rate < threshold and company.contact_email:
            notif.notify('attendance.low', [{'email': company.contact_email}], {
                'company_name': company.name, 'rate': rate,
                'threshold': threshold, 'date': str(today),
                'report_url': '',
            }, channels=('email',), company_id=company.id,
                related=('attendance_report', str(today)))
            alerts.append(f'{company.name}: {rate}%')
    return f'Low-attendance alerts sent: {alerts or "none"}'
