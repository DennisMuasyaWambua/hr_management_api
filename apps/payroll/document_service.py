"""
Payroll document orchestration: render PDF/Excel via apps.core.services.documents,
password-protect PDFs, persist PayrollDocument rows with SHA-256 fingerprints.
"""
import secrets

from django.core.files.base import ContentFile

from apps.core.models import ServiceAuditLog
from apps.payroll.services import documents as docsvc

from .approval_models import PayrollDocument
from .models import Company, PayrollRun


def _records(run):
    return list(run.records.select_related('employee').filter(is_deleted=False))


def generate_run_documents(run: PayrollRun, *, triggered_by=None,
                           pdf_password: str | None = None) -> PayrollDocument:
    """
    Generate the canonical payroll PDF (password-protected) and Excel for a
    run. Returns the PDF PayrollDocument (Excel saved alongside).
    Refuses to regenerate documents on a locked (paid) run.
    """
    if PayrollDocument.objects.filter(payroll_run_id=run.id,
                                      is_locked=True).exists():
        raise PermissionError('Documents for this run are locked (run is paid).')

    company = Company.objects.filter(id=run.company_id).first()
    company_name = company.name if company else ''
    records = _records(run)

    pdf_bytes = docsvc.generate_payroll_pdf(
        run, records, company_name=company_name,
        triggered_by=str(triggered_by or run.run_by))
    password = pdf_password or secrets.token_urlsafe(9)
    protected = docsvc.password_protect_pdf(pdf_bytes, password)

    pdf_doc = PayrollDocument(
        payroll_run_id=run.id, company_id=run.company_id, tenant_id=run.tenant_id,
        doc_type='payroll_pdf', sha256=docsvc.sha256_of(protected),
        password_protected=True, generated_by=triggered_by)
    pdf_doc.file.save(f'payroll_{run.period_year}_{run.period_month}_{run.id}.pdf',
                      ContentFile(protected), save=True)

    excel_bytes = docsvc.generate_payroll_excel(run, records,
                                                company_name=company_name)
    xl_doc = PayrollDocument(
        payroll_run_id=run.id, company_id=run.company_id, tenant_id=run.tenant_id,
        doc_type='payroll_excel', sha256=docsvc.sha256_of(excel_bytes),
        generated_by=triggered_by)
    xl_doc.file.save(f'payroll_{run.period_year}_{run.period_month}_{run.id}.xlsx',
                     ContentFile(excel_bytes), save=True)

    ServiceAuditLog.log('payroll.documents_generated',
                        object_type='PayrollRun', object_id=str(run.id),
                        company_id=run.company_id, actor_user_id=triggered_by,
                        metadata={'pdf_sha256': pdf_doc.sha256,
                                  'excel_sha256': xl_doc.sha256,
                                  'pdf_password': password})  # password retrievable by HR via audit
    return pdf_doc


def run_minimum_wage_check(run: PayrollRun):
    """
    Flag any employee in this run paid below the legal minimum for their job
    category (best-effort match on job_title). Creates ComplianceAlerts and
    notifies HR. Called on calculate/submit.
    """
    from apps.core.services import notifications as notif
    from apps.hr.models import ComplianceAlert, MinimumWage

    company = Company.objects.filter(id=run.company_id).first()
    alerts = []
    wages = list(MinimumWage.objects.all())
    if not wages:
        return []
    for rec in _records(run):
        title = (rec.employee.job_title or '').lower()
        match = next((w for w in wages
                      if w.job_category.lower() in title
                      or title in w.job_category.lower()), None)
        if match and rec.gross_salary < match.monthly_amount:
            alert, created = ComplianceAlert.objects.get_or_create(
                alert_type='below_minimum_wage', employee_id=rec.employee_id,
                payroll_run_id=run.id, company_id=run.company_id,
                defaults={'tenant_id': run.tenant_id, 'details': {
                    'gross': str(rec.gross_salary),
                    'minimum': str(match.monthly_amount),
                    'category': match.job_category,
                    'period': run.period_display}})
            if created:
                alerts.append(alert)
                if company and company.contact_email:
                    notif.notify('compliance.minimum_wage',
                                 [{'email': company.contact_email}],
                                 {'employee_number': rec.employee.employee_number,
                                  'job_title': rec.employee.job_title,
                                  'gross': str(rec.gross_salary),
                                  'minimum': str(match.monthly_amount),
                                  'category': match.job_category},
                                 channels=('email',), company_id=run.company_id,
                                 related=('compliance_alert', alert.id))
    return alerts
