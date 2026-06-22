"""
Payroll approval quorum logic — single source of truth used by the approvals
API, the one-tap token handler, and the DocuSeal webhook.
"""
import logging

from django.db import transaction
from django.utils import timezone

from apps.core.models import OneTapToken, ServiceAuditLog
from apps.core.services import notifications as notif

from .approval_models import (ApproverConfig, PayrollApproval, PayrollApprover,
                              PayrollDocument)
from .models import Company, PayrollRun

logger = logging.getLogger(__name__)


class ApprovalError(Exception):
    pass


def submit_for_approval(run: PayrollRun, *, triggered_by=None, request=None) -> dict:
    """
    draft/calculated → pending_approval. Generates the payroll PDF, opens a
    DocuSeal submission, and notifies every configured approver (email + SMS
    with one-tap link + DocuSeal signing link).
    """
    if run.status not in ('draft', 'calculated'):
        raise ApprovalError(f'Run is {run.status}; only draft/calculated can be submitted.')
    config = ApproverConfig.objects.filter(company_id=run.company_id,
                                           is_active=True).first()
    if config is None or not config.approvers.filter(is_active=True).exists():
        raise ApprovalError('No approver configuration for this company. '
                            'Create one at api/approver-config/ first.')

    from .document_service import generate_run_documents
    doc = generate_run_documents(run, triggered_by=triggered_by)

    approvers = list(config.approvers.filter(is_active=True))
    docuseal_links = _open_docuseal_submission(run, doc, approvers)

    run.status = 'pending_approval'
    run.save(update_fields=['status', 'updated_at'])

    company = Company.objects.filter(id=run.company_id).first()
    company_name = company.name if company else ''
    items, count, totals = _run_summary(run)
    for approver in approvers:
        token = OneTapToken.issue('payroll.approve', run.id, approver.user_id,
                                  company_id=run.company_id, tenant_id=run.tenant_id)
        from django.conf import settings
        base = getattr(settings, 'PUBLIC_API_BASE_URL', 'http://localhost:8000')
        # Demo DocuSeal submissions return a stub 'docuseal.demo' URL that
        # doesn't exist; fall back to the always-functional one-tap link.
        signing_url = docuseal_links.get(approver.email, '')
        approve_url = (signing_url
                       if signing_url and 'docuseal.demo' not in signing_url
                       else f'{base}/api/one-tap/{token.token}/')
        # Plain-text email with a per-employee deduction breakdown (EmailJS
        # escapes {{message}}, so HTML would show as raw tags).
        subject = (f'Payroll {run.period_display} — {company_name}: '
                   f'review, sign & approve ({count} employee'
                   f'{"s" if count != 1 else ""})')
        body = _approval_email_text(company_name, run.period_display, items,
                                    count, totals, config.required_approvals,
                                    approve_url)
        if approver.email:
            notif.send_email(approver.email, subject, body,
                             event='payroll.pending_approval',
                             company_id=run.company_id, tenant_id=run.tenant_id,
                             related=('payroll_run', run.id))
        # SMS stays a short link only — payroll figures must never go over SMS.
        if approver.phone:
            notif.send_sms(approver.phone,
                           f'Payroll {run.period_display} ({company_name}) needs your '
                           f'approval & signature. Review & sign: {approve_url}',
                           event='payroll.pending_approval',
                           company_id=run.company_id, tenant_id=run.tenant_id,
                           related=('payroll_run', run.id))

    ServiceAuditLog.log('payroll.submitted_for_approval', request=request,
                        object_type='PayrollRun', object_id=str(run.id),
                        company_id=run.company_id,
                        actor_user_id=triggered_by,
                        metadata={'required_approvals': config.required_approvals,
                                  'approvers': len(approvers),
                                  'document_sha256': doc.sha256})
    return {'status': run.status, 'approvers_notified': len(approvers),
            'required_approvals': config.required_approvals,
            'document_id': str(doc.id)}


def _employee_name(emp) -> str:
    """Resolve a display name for an employee. Names live on AppUser
    (linked by AppUser.employee_id == EmployeeProfile.id); fall back to the
    employee number when no user account exists."""
    from apps.core.models import AppUser
    au = AppUser.objects.filter(employee_id=emp.id).first()
    if au and au.full_name:
        return au.full_name
    return emp.employee_number or 'Employee'


def _run_summary(run):
    """Return (items, count, totals) for a run. Each item is a dict with name,
    role, gross, paye, nssf, nhif, helb, other, deductions, net. `totals` holds
    the column sums. Shared by the email and the approval page."""
    from decimal import Decimal
    z = Decimal('0')
    items = []
    totals = {k: Decimal('0') for k in
              ('gross', 'paye', 'nssf', 'nhif', 'helb', 'other', 'deductions', 'net')}
    for rec in run.records.select_related('employee').filter(is_deleted=False):
        emp = rec.employee
        g = rec.gross_salary or z
        n = rec.net_salary or z
        it = {'name': _employee_name(emp),
              'role': emp.job_title or emp.employee_number,
              'gross': g, 'paye': rec.paye or z, 'nssf': rec.nssf or z,
              'nhif': rec.nhif or z, 'helb': rec.helb or z,
              'other': rec.other_deductions or z, 'deductions': g - n, 'net': n}
        items.append(it)
        for k in totals:
            totals[k] += it[k]
    return items, len(items), totals


_EMAIL_COLS = [('name', 'Employee', 'left'), ('role', 'Role', 'left'),
               ('gross', 'Gross', 'right'), ('paye', 'PAYE', 'right'),
               ('nssf', 'NSSF', 'right'), ('nhif', 'NHIF', 'right'),
               ('helb', 'HELB', 'right'), ('net', 'Net Pay', 'right')]


def _employee_rows(run):
    """HTML table rows for the approval page. Returns (rows, count, totals)."""
    items, count, totals = _run_summary(run)
    rows = ''.join(
        '<tr>' + ''.join(
            f'<td style="padding:6px 8px;border-bottom:1px solid #eee;'
            f'text-align:{align}">'
            f'{it[key] if key in ("name", "role") else "KES " + format(it[key], ",.2f")}'
            f'</td>'
            for key, _h, align in _EMAIL_COLS) + '</tr>'
        for it in items)
    return rows, count, totals


def _money(v) -> str:
    return f'KES {v:,.2f}'


def _approval_email_text(company_name, period, items, count, totals,
                         required, approve_url) -> str:
    """Plain-text payroll approval email with a per-employee deduction
    breakdown. EmailJS escapes {{message}} and renders newlines as line breaks,
    so the body is plain text (no HTML). The link is the DocuSeal signing page
    when DocuSeal is configured, otherwise the one-tap approval page."""
    sep = '=' * 44
    lines = [
        f'Payroll {period} — {company_name}',
        'This payroll is ready for your approval and e-signature.',
        '',
        f'EMPLOYEES ({count})',
        sep,
    ]
    for it in items:
        lines.append(f'{it["name"]} — {it["role"]}')
        lines.append(f'    Gross:   {_money(it["gross"])}')
        lines.append(f'    PAYE:    {_money(it["paye"])}')
        lines.append(f'    NSSF:    {_money(it["nssf"])}')
        lines.append(f'    NHIF:    {_money(it["nhif"])}')
        lines.append(f'    HELB:    {_money(it["helb"])}')
        lines.append(f'    Net pay: {_money(it["net"])}')
        lines.append('')
    lines += [
        sep,
        'TOTALS',
        f'    Gross pay:        {_money(totals["gross"])}',
        f'    PAYE:             {_money(totals["paye"])}',
        f'    NSSF:             {_money(totals["nssf"])}',
        f'    NHIF:             {_money(totals["nhif"])}',
        f'    HELB:             {_money(totals["helb"])}',
        f'    Total deductions: {_money(totals["deductions"])}',
        f'    Net pay:          {_money(totals["net"])}',
        '',
        f'Approvals required: {required}',
        '',
        'Review the payroll and add your e-signature here:',
        approve_url,
        '',
        'Sheer Logic HR',
    ]
    return '\n'.join(lines)


def _open_docuseal_submission(run, doc, approvers) -> dict:
    """Create DocuSeal template+submission; returns {email: signing_url}."""
    from apps.core.services import docuseal
    from apps.payroll.services import documents as docsvc
    try:
        # DocuSeal rejects password-protected PDFs ("422 File is password
        # protected"), so send a freshly rendered UNprotected copy of the
        # payslip for signing. The protected copy stays stored for distribution.
        records = list(run.records.select_related('employee').filter(is_deleted=False))
        company = Company.objects.filter(id=run.company_id).first()
        pdf_bytes = docsvc.generate_payroll_pdf(
            run, records, company_name=(company.name if company else ''),
            triggered_by=str(run.run_by))
        template = docuseal.create_template_from_pdf(
            f'Payroll {run.period_display} ({run.id})', pdf_bytes)
        # send_email=False: our own plain-text email carries the DocuSeal
        # signing link, so DocuSeal shouldn't also email the signer.
        submission = docuseal.create_submission(
            template['id'],
            [{'name': a.name, 'email': a.email, 'phone': a.phone}
             for a in approvers],
            send_email=False,
            metadata={'payroll_run_id': str(run.id)})
        doc.docuseal_template_id = str(template['id'])
        doc.docuseal_submission_id = str(submission['id'])
        doc.save(update_fields=['docuseal_template_id', 'docuseal_submission_id',
                                'updated_at'])
        return {s.get('email'): s.get('embed_src', '')
                for s in submission.get('submitters', [])}
    except Exception as exc:  # noqa: BLE001 — approval flow must survive DocuSeal outage
        logger.exception('DocuSeal submission failed for run %s', run.id)
        return {}


@transaction.atomic
def record_approval(payroll_run_id, approver_user_id, *, via='dashboard',
                    decision='approved', comment='', docuseal_slug='',
                    signature_image='', request=None) -> dict:
    """
    Record one approver's decision; flip the run to `approved` when quorum is
    reached. Idempotent per (run, approver) — duplicate signatures are no-ops.
    """
    try:
        run = PayrollRun.objects.get(id=payroll_run_id)
    except PayrollRun.DoesNotExist:
        return {'error': 'payroll run not found'}
    if run.status != 'pending_approval':
        return {'error': f'run is {run.status}, not pending_approval'}

    config = ApproverConfig.objects.filter(company_id=run.company_id).first()
    if config is None:
        return {'error': 'no approver config'}
    if not config.approvers.filter(user_id=approver_user_id,
                                   is_active=True).exists():
        return {'error': 'not a configured approver for this company'}

    _, created = PayrollApproval.objects.get_or_create(
        payroll_run_id=run.id, approver_user_id=approver_user_id,
        defaults={'decision': decision, 'via': via, 'comment': comment,
                  'company_id': run.company_id, 'tenant_id': run.tenant_id,
                  'docuseal_submitter_slug': docuseal_slug,
                  'signature_image': signature_image or '',
                  'ip_address': _ip(request)})
    if not created:
        return {'status': 'duplicate', 'note': 'approval already recorded'}

    ServiceAuditLog.log(f'payroll.approval_{decision}', request=request,
                        object_type='PayrollRun', object_id=str(run.id),
                        company_id=run.company_id,
                        actor_user_id=approver_user_id,
                        metadata={'via': via})

    if decision == 'rejected':
        run.status = 'draft'
        run.save(update_fields=['status', 'updated_at'])
        return {'status': 'rejected', 'run_status': run.status}

    approvals = PayrollApproval.objects.filter(
        payroll_run_id=run.id, decision='approved').count()
    if approvals >= config.required_approvals:
        run.status = 'approved'
        run.save(update_fields=['status', 'updated_at'])
        _finalize_signed_documents(run)
        company = Company.objects.filter(id=run.company_id).first()
        if company and company.contact_email:
            notif.notify('payroll.approved', [{'email': company.contact_email}],
                         {'period': run.period_display,
                          'company_name': company.name},
                         channels=('email',), company_id=run.company_id,
                         related=('payroll_run', run.id))
        ServiceAuditLog.log('payroll.quorum_reached',
                            object_type='PayrollRun', object_id=str(run.id),
                            company_id=run.company_id,
                            metadata={'approvals': approvals,
                                      'required': config.required_approvals})
    return {'status': 'approved', 'approvals': approvals,
            'required': config.required_approvals, 'run_status': run.status}


def _finalize_signed_documents(run: PayrollRun):
    """
    Quorum reached → the run is e-signed. Mark every document as signed (this is
    the signal the disbursement gate checks) and best-effort fetch + store the
    signed/audit-trailed PDF from DocuSeal. Survives DocuSeal/demo outages.
    """
    import hashlib

    from django.core.files.base import ContentFile

    from apps.core.services import docuseal

    docs = list(PayrollDocument.objects.filter(payroll_run_id=run.id))
    PayrollDocument.objects.filter(payroll_run_id=run.id).update(
        is_signed=True, updated_at=timezone.now())

    submission_id = next((d.docuseal_submission_id for d in docs
                          if d.docuseal_submission_id), '')
    if not submission_id:
        return
    try:
        signed_bytes = docuseal.get_signed_document(submission_id)
    except Exception:  # noqa: BLE001 — never block approval on a download error
        logger.exception('Could not fetch signed document for run %s', run.id)
        return
    if not signed_bytes:
        return  # demo mode / not yet available
    if PayrollDocument.objects.filter(payroll_run_id=run.id,
                                      doc_type='signed_pdf').exists():
        return
    template_doc = docs[0] if docs else None
    PayrollDocument.objects.create(
        tenant_id=run.tenant_id, company_id=run.company_id,
        payroll_run_id=run.id, doc_type='signed_pdf',
        file=ContentFile(signed_bytes, name=f'payroll_{run.id}_signed.pdf'),
        sha256=hashlib.sha256(signed_bytes).hexdigest(),
        docuseal_submission_id=submission_id,
        docuseal_template_id=getattr(template_doc, 'docuseal_template_id', ''),
        is_signed=True,
        generated_by=getattr(template_doc, 'generated_by', None),
    )


def lock_documents(run: PayrollRun):
    """Once paid: lock every document for the run (immutable, audit kept)."""
    updated = PayrollDocument.objects.filter(payroll_run_id=run.id) \
        .update(is_locked=True, updated_at=timezone.now())
    ServiceAuditLog.log('payroll.documents_locked',
                        object_type='PayrollRun', object_id=str(run.id),
                        company_id=run.company_id,
                        metadata={'documents': updated})
    return updated


def _ip(request):
    if request is None:
        return None
    return request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip() \
        or request.META.get('REMOTE_ADDR')
