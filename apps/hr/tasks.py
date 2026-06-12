"""
HR periodic tasks (registered on Celery beat in hr_api/celery.py):
  - reset_variable_allowances : 1st of month 00:05 — per-diem style resets
  - certificate_expiry_alerts : daily 07:00 — alert HR before lapse
"""
from celery import shared_task
from django.utils import timezone


@shared_task
def reset_variable_allowances():
    """
    Month-end reset for variable allowances (e.g. per diem): close out last
    month's variable allowance rows so they don't roll into the new month.
    """
    from apps.hr.models import EmployeeAllowance

    today = timezone.localdate()
    first_of_month = today.replace(day=1)
    last_month_end = first_of_month - timezone.timedelta(days=1)

    qs = EmployeeAllowance.objects.filter(
        allowance_type__is_variable=True, is_active=True,
    ).filter(effective_to__isnull=True)
    count = qs.update(effective_to=last_month_end, is_active=False)
    return f'Reset {count} variable allowances as of {last_month_end}'


@shared_task
def certificate_expiry_alerts():
    """Daily scan: notify HR for certificates inside their alert window."""
    from apps.core.services import notifications as notif
    from apps.hr.models import ComplianceAlert, EmployeeCertificate
    from apps.payroll.models import Company

    today = timezone.localdate()
    sent = 0
    qs = EmployeeCertificate.objects.filter(is_active=True,
                                            expiry_date__isnull=False)
    for cert in qs:
        window_start = cert.expiry_date - timezone.timedelta(days=cert.alert_days_before)
        if not (window_start <= today <= cert.expiry_date):
            continue
        # Throttle: at most one alert per 7 days per certificate.
        if cert.last_alert_sent_at and \
                (timezone.now() - cert.last_alert_sent_at).days < 7:
            continue
        company = Company.objects.filter(id=cert.company_id).first()
        hr_email = company.contact_email if company else None
        if hr_email:
            notif.notify('certificate.expiring', [{'email': hr_email}], {
                'certificate_name': cert.name,
                'employee_name': str(cert.employee_id)[:8],
                'expiry_date': str(cert.expiry_date),
            }, channels=('email',), company_id=cert.company_id,
                related=('employee_certificate', cert.id))
        ComplianceAlert.objects.get_or_create(
            alert_type='certificate_expired', employee_id=cert.employee_id,
            company_id=cert.company_id, status='open',
            details={'certificate': cert.name, 'expiry': str(cert.expiry_date)})
        cert.last_alert_sent_at = timezone.now()
        cert.save(update_fields=['last_alert_sent_at', 'updated_at'])
        sent += 1
    return f'Sent {sent} certificate expiry alerts'
