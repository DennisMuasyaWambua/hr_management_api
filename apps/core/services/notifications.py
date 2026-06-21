"""
Unified multi-channel notification service.

Channels:
  - email     : Django SMTP (Resend SMTP-compatible) with attachment support
  - sms       : Africa's Talking SMS REST API
  - whatsapp  : Africa's Talking Chat API (WhatsApp product)

All sends are recorded in NotificationLog. Use `notify()` for template-based
events, or `send_*` for direct sends. Payroll figures must never be sent in
full over SMS/WhatsApp — only references/links (see LOGIC_AUDIT.md).
"""
import logging

import requests
from django.conf import settings
from django.core.mail import EmailMessage

from apps.core.models import NotificationLog, NotificationTemplate

logger = logging.getLogger(__name__)

AT_SMS_URL_LIVE = 'https://api.africastalking.com/version1/messaging'
AT_SMS_URL_SANDBOX = 'https://api.sandbox.africastalking.com/version1/messaging'
AT_WHATSAPP_URL = 'https://chat.africastalking.com/whatsapp/message/send'

# Built-in fallback templates used when no NotificationTemplate row matches.
DEFAULT_TEMPLATES = {
    'leave.requested': {
        'subject': 'Leave request from {employee_name}',
        'body': ('{employee_name} requested {leave_type} leave '
                 '({start_date} to {end_date}). Approve: {approve_url}'),
    },
    'leave.recall_requested': {
        'subject': 'Leave recall for {employee_name}',
        'body': ('Recall requested for {employee_name} (leave {start_date}–{end_date}). '
                 'Approve: {approve_url}'),
    },
    'overtime.requested': {
        'subject': 'Overtime approval needed: {employee_name}',
        'body': ('{employee_name} logged {hours}h overtime on {date}. '
                 'Approve: {approve_url}'),
    },
    'payroll.pending_approval': {
        'subject': 'Payroll {period} awaiting your approval',
        'body': ('Payroll for {period} at {company_name} needs your signature '
                 '({approvals_count}/{required_approvals} so far). Review: {approve_url}'),
    },
    'payroll.approved': {
        'subject': 'Payroll {period} fully approved',
        'body': 'Payroll {period} at {company_name} reached approval quorum and is ready to pay.',
    },
    'certificate.expiring': {
        'subject': 'Certificate expiring: {certificate_name} ({employee_name})',
        'body': ('{certificate_name} for {employee_name} expires on {expiry_date}. '
                 'Please arrange renewal.'),
    },
    'attendance.low': {
        'subject': 'Low attendance alert: {company_name} at {rate}%',
        'body': ('Attendance for {company_name} on {date} is {rate}% '
                 '(threshold {threshold}%). Report attached/linked: {report_url}'),
    },
    'compliance.minimum_wage': {
        'subject': 'Minimum wage alert: {employee_number}',
        'body': ('Employee {employee_number} ({job_title}) gross {gross} is below the '
                 'legal minimum {minimum} for category "{category}".'),
    },
    'share.document': {
        'subject': '{document_title} from {company_name}',
        'body': '{message}\n\nThis document was shared with you via Sheer Logic HR.',
    },
}


def _resolve_template(event, channel, company_id=None):
    tpl = None
    if company_id:
        tpl = NotificationTemplate.objects.filter(
            company_id=company_id, event=event, channel=channel, is_active=True
        ).first()
    if tpl is None:
        tpl = NotificationTemplate.objects.filter(
            company_id__isnull=True, event=event, channel=channel, is_active=True
        ).first()
    if tpl is not None:
        return tpl
    default = DEFAULT_TEMPLATES.get(event)
    if default is None:
        return None
    fake = NotificationTemplate(event=event, channel=channel,
                                subject=default['subject'], body=default['body'])
    return fake


def _log(channel, recipient, subject, body, *, event='', company_id=None,
         tenant_id=None, source_app='system', related=None):
    related_type, related_id = related or ('', '')
    return NotificationLog.objects.create(
        channel=channel, recipient=recipient, subject=subject or '', body=body or '',
        event=event, company_id=company_id, tenant_id=tenant_id, source_app=source_app,
        related_object_type=related_type, related_object_id=str(related_id),
    )


def _mark(log, *, status, provider_message_id='', error=''):
    log.status = status
    log.attempts += 1
    log.provider_message_id = provider_message_id or log.provider_message_id
    log.error = error
    log.save(update_fields=['status', 'attempts', 'provider_message_id', 'error', 'updated_at'])
    return log


# ---------------------------------------------------------------------------
# Channel senders
# ---------------------------------------------------------------------------

def send_email(recipient, subject, body, *, attachments=None, log=None, **log_kwargs):
    """attachments: list of (filename, content_bytes, mimetype)."""
    log = log or _log('email', recipient, subject, body, **log_kwargs)
    try:
        msg = EmailMessage(
            subject=subject, body=body,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', None),
            to=[recipient],
        )
        for att in attachments or []:
            msg.attach(*att)
        msg.send(fail_silently=False)
        return _mark(log, status='sent')
    except Exception as exc:  # noqa: BLE001 - log + surface via status
        logger.exception('Email send failed to %s', recipient)
        return _mark(log, status='failed', error=str(exc))


def _at_headers():
    return {
        'apiKey': settings.AT_API_KEY,
        'Accept': 'application/json',
    }


def send_sms(recipient, body, *, log=None, **log_kwargs):
    log = log or _log('sms', recipient, '', body, **log_kwargs)
    url = AT_SMS_URL_SANDBOX if settings.AT_USERNAME == 'sandbox' else AT_SMS_URL_LIVE
    payload = {'username': settings.AT_USERNAME, 'to': recipient, 'message': body}
    if settings.AT_SENDER_ID:
        payload['from'] = settings.AT_SENDER_ID
    try:
        resp = requests.post(url, data=payload, headers=_at_headers(), timeout=30)
        data = resp.json() if resp.content else {}
        recipients = (data.get('SMSMessageData') or {}).get('Recipients') or []
        ok = resp.ok and recipients and recipients[0].get('statusCode') in (100, 101, 102)
        message_id = recipients[0].get('messageId', '') if recipients else ''
        if ok:
            return _mark(log, status='sent', provider_message_id=message_id)
        return _mark(log, status='failed',
                     error=f"HTTP {resp.status_code}: {resp.text[:500]}")
    except Exception as exc:  # noqa: BLE001
        logger.exception('SMS send failed to %s', recipient)
        return _mark(log, status='failed', error=str(exc))


def send_whatsapp(recipient, body, *, log=None, **log_kwargs):
    """
    Africa's Talking Chat API (WhatsApp). Requires an onboarded WhatsApp
    sender number (AT_WHATSAPP_NUMBER). Falls back to SMS when not configured
    so flows never silently drop a notification.
    """
    wa_number = getattr(settings, 'AT_WHATSAPP_NUMBER', '')
    if not wa_number:
        logger.info('WhatsApp not configured; falling back to SMS for %s', recipient)
        return send_sms(recipient, body, **log_kwargs)
    log = log or _log('whatsapp', recipient, '', body, **log_kwargs)
    payload = {
        'username': settings.AT_USERNAME,
        'waNumber': wa_number,
        'phoneNumber': recipient,
        'body': {'message': body},
    }
    try:
        resp = requests.post(AT_WHATSAPP_URL, json=payload, headers=_at_headers(), timeout=30)
        data = resp.json() if resp.content else {}
        if resp.ok and str(data.get('status', '')).lower() in ('sent', 'queued', 'success'):
            return _mark(log, status='sent', provider_message_id=str(data.get('messageId', '')))
        return _mark(log, status='failed', error=f"HTTP {resp.status_code}: {resp.text[:500]}")
    except Exception as exc:  # noqa: BLE001
        logger.exception('WhatsApp send failed to %s', recipient)
        return _mark(log, status='failed', error=str(exc))


SENDERS = {'email': send_email, 'sms': send_sms, 'whatsapp': send_whatsapp}


# ---------------------------------------------------------------------------
# High-level event API
# ---------------------------------------------------------------------------

def notify(event, recipients, context=None, *, channels=('email',), company_id=None,
           tenant_id=None, source_app='system', related=None, attachments=None,
           async_send=True):
    """
    Render the template for `event` per channel and dispatch to recipients.

    recipients: list of dicts {'email': ..., 'phone': ...} — each channel picks
    the address it needs and skips recipients without one.
    Returns the created NotificationLog ids.
    """
    context = context or {}
    log_ids = []
    for channel in channels:
        tpl = _resolve_template(event, channel, company_id)
        if tpl is None:
            logger.warning('No template for event=%s channel=%s', event, channel)
            continue
        subject, body = tpl.render(context)
        for r in recipients:
            address = r.get('email') if channel == 'email' else r.get('phone')
            if not address:
                continue
            log = _log(channel, address, subject if channel == 'email' else '', body,
                       event=event, company_id=company_id, tenant_id=tenant_id,
                       source_app=source_app, related=related)
            log_ids.append(str(log.id))
            if async_send:
                from apps.core.tasks import deliver_notification
                try:
                    deliver_notification.delay(str(log.id))
                except Exception:
                    # Celery/broker unavailable (e.g. no Redis on the host) must
                    # never crash the caller — deliver synchronously instead.
                    logger.warning('Async notification dispatch failed; sending '
                                   'synchronously for log %s', log.id, exc_info=True)
                    try:
                        deliver_notification(str(log.id))
                    except Exception:
                        logger.exception('Synchronous notification fallback failed '
                                         'for log %s', log.id)
            else:
                kwargs = {'log': log}
                if channel == 'email':
                    kwargs['attachments'] = attachments
                SENDERS[channel](address, *( (subject, body) if channel == 'email' else (body,) ), **kwargs)
    return log_ids
