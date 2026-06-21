"""
Background-check validation round-trip.

Sheer Logic renders a branded request letter for a subject and opens a DocuSeal
submission addressed to the relevant validation body. The body signs, ticks
whether the subject is clean, and (if not) leaves comments. DocuSeal's webhook
(apps.payroll.views_approvals.DocuSealWebhook) routes the completed submission
back here via metadata.background_check_id, and we record the verdict.
"""
import io
import logging

from django.utils import timezone

from apps.core.models import ServiceAuditLog
from apps.core.services import docuseal

from .models import BackgroundCheck

logger = logging.getLogger(__name__)

# Fields the validation body fills on the DocuSeal document.
VALIDATION_FIELDS = [
    {'name': 'Subject is clean', 'type': 'checkbox'},
    {'name': 'Comments', 'type': 'text'},
    {'name': 'Signature', 'type': 'signature'},
]


class ValidationError(Exception):
    pass


def _subject_name(check: BackgroundCheck) -> str:
    """Best-effort human name for the subject of the check."""
    try:
        if check.employee_id:
            from apps.payroll.models import EmployeeProfile
            emp = EmployeeProfile.objects.filter(id=check.employee_id).first()
            if emp:
                return f'{emp.employee_number} — {emp.job_title}'
        if check.candidate_id:
            from apps.recruitment.models import Candidate
            cand = Candidate.objects.filter(id=check.candidate_id).first()
            if cand:
                return getattr(cand, 'full_name', None) or getattr(cand, 'name', '') or str(cand.id)
    except Exception:  # noqa: BLE001
        logger.exception('Could not resolve subject name for check %s', check.id)
    return str(check.employee_id or check.candidate_id or check.id)


def render_validation_letter(check: BackgroundCheck, subject_name: str) -> bytes:
    """A simple Sheer Logic-branded request letter (reportlab)."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    y = height - 30 * mm

    c.setFillColorRGB(0.094, 0.180, 0.353)  # Sheer Logic navy
    c.setFont('Helvetica-Bold', 20)
    c.drawString(25 * mm, y, 'SHEER LOGIC')
    c.setFont('Helvetica', 9)
    c.setFillColorRGB(0.4, 0.4, 0.4)
    c.drawString(25 * mm, y - 6 * mm, 'Background Verification Request')

    c.setFillColorRGB(0, 0, 0)
    c.setFont('Helvetica', 11)
    y -= 25 * mm
    lines = [
        f'Date: {timezone.localdate().isoformat()}',
        f'To: {check.validation_body_name or "Validation Body"}',
        '',
        'Dear Sir/Madam,',
        '',
        f'Sheer Logic requests verification of the following subject as part of a '
        f'{check.get_check_type_display().lower()} background check:',
        '',
        f'    Subject: {subject_name}',
        f'    Reference: {check.id}',
        '',
        'Please confirm whether the subject is CLEAN by signing below. If the '
        'subject is NOT clean, kindly tick accordingly and leave comments '
        'explaining the findings, then return the signed document to Sheer Logic.',
        '',
        'Thank you for your cooperation.',
        '',
        'Yours faithfully,',
        'Sheer Logic Management Solutions',
    ]
    for line in lines:
        c.drawString(25 * mm, y, line)
        y -= 7 * mm

    c.showPage()
    c.save()
    buf.seek(0)
    return buf.read()


def send_for_validation(check: BackgroundCheck, *, validation_body_name=None,
                        validation_body_email=None, request=None) -> dict:
    """Open a DocuSeal submission to the validation body and mark in_progress."""
    name = validation_body_name or check.validation_body_name
    email = validation_body_email or check.validation_body_email
    if not email:
        raise ValidationError('A validation_body_email is required to send the request.')

    check.validation_body_name = name or ''
    check.validation_body_email = email

    subject_name = _subject_name(check)
    pdf_bytes = render_validation_letter(check, subject_name)

    template = docuseal.create_template_from_pdf(
        f'Background check {check.id}', pdf_bytes,
        fields=VALIDATION_FIELDS, role='Validator')
    submission = docuseal.create_submission(
        template['id'],
        [{'name': name or '', 'email': email}],
        metadata={'background_check_id': str(check.id)})

    check.docuseal_submission_id = str(submission.get('id', ''))
    check.provider_name = 'docuseal'
    check.provider_reference = check.docuseal_submission_id
    check.status = 'in_progress'
    check.save(update_fields=['validation_body_name', 'validation_body_email',
                              'docuseal_submission_id', 'provider_name',
                              'provider_reference', 'status', 'updated_at'])

    ServiceAuditLog.log('background_check.validation_requested', request=request,
                        object_type='BackgroundCheck', object_id=str(check.id),
                        company_id=check.company_id,
                        metadata={'validation_body': email,
                                  'submission_id': check.docuseal_submission_id})
    submitters = submission.get('submitters', [])
    return {'status': check.status,
            'submission_id': check.docuseal_submission_id,
            'signing_url': submitters[0].get('embed_src', '') if submitters else ''}


def record_validation_result(check: BackgroundCheck, *, is_clean: bool,
                             comments: str = '', signed_url: str = '',
                             request=None) -> dict:
    """Apply a returned validation decision to the background check."""
    check.verdict = 'clean' if is_clean else 'not_clean'
    check.reviewer_comments = comments or ''
    check.status = 'passed' if is_clean else 'failed'
    check.completed_at = timezone.now()
    if is_clean:
        check.clearance_date = timezone.localdate()
    if signed_url:
        check.signed_document_url = signed_url
    check.result_summary = (
        'Cleared by validation body' if is_clean
        else f'Not clean: {comments[:500]}')
    check.save(update_fields=['verdict', 'reviewer_comments', 'status',
                              'completed_at', 'clearance_date',
                              'signed_document_url', 'result_summary',
                              'updated_at'])

    ServiceAuditLog.log('background_check.validation_recorded', request=request,
                        object_type='BackgroundCheck', object_id=str(check.id),
                        company_id=check.company_id,
                        metadata={'verdict': check.verdict})
    return {'status': check.status, 'verdict': check.verdict}
