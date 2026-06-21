"""
DocuSeal e-signature client (https://www.docuseal.com / self-hosted).

Flow:
  1. create_submission_from_pdf() — uploads the rendered payroll PDF and
     creates a submission with one submitter per approver.
  2. DocuSeal emails/links each approver; signatures happen on DocuSeal.
  3. DocuSeal calls our webhook (apps.payroll.views_approvals.DocuSealWebhook)
     on each completed signature → we record a PayrollApproval and check quorum.

Configuration (env):
  DOCUSEAL_BASE_URL   default https://api.docuseal.com (self-hosted: your URL + /api)
  DOCUSEAL_API_KEY    X-Auth-Token
  DOCUSEAL_DEMO_MODE  when true, no HTTP call is made; returns a stub so the
                      flow can be demonstrated without a DocuSeal account.
"""
import base64
import logging
import uuid

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class DocuSealError(Exception):
    pass


def _base_url():
    return getattr(settings, 'DOCUSEAL_BASE_URL', 'https://api.docuseal.com').rstrip('/')


def _headers():
    return {'X-Auth-Token': getattr(settings, 'DOCUSEAL_API_KEY', ''),
            'Content-Type': 'application/json'}


def _demo():
    return getattr(settings, 'DOCUSEAL_DEMO_MODE', True)


def create_template_from_pdf(name: str, pdf_bytes: bytes, *, fields=None,
                             role='Approver') -> dict:
    """
    Create a DocuSeal template from a PDF.

    `fields` lets callers append fields beyond the default signature, e.g. the
    background-check flow adds a "clean?" decision + a comments box:
        fields=[{'name': 'Signature', 'type': 'signature'},
                {'name': 'Subject is clean', 'type': 'checkbox'},
                {'name': 'Comments', 'type': 'text'}]
    The signer role is applied to every field.
    """
    if fields is None:
        fields = [{'name': 'Signature', 'type': 'signature'}]
    fields = [{**f, 'role': f.get('role', role)} for f in fields]
    if _demo():
        return {'id': f'demo-tpl-{uuid.uuid4().hex[:8]}', 'name': name, 'demo': True}
    resp = requests.post(
        f'{_base_url()}/templates/pdf',
        headers=_headers(),
        json={
            'name': name,
            'documents': [{
                'name': name,
                'file': base64.b64encode(pdf_bytes).decode(),
                'fields': fields,
            }],
        },
        timeout=60,
    )
    if not resp.ok:
        raise DocuSealError(f'Template create failed: {resp.status_code} {resp.text[:300]}')
    return resp.json()


def create_submission(template_id, approvers: list[dict], *, send_email=True,
                      metadata=None) -> dict:
    """
    approvers: [{'name': ..., 'email': ..., 'phone': ...}, ...]
    Returns the DocuSeal submission payload (one submitter per approver).
    """
    if _demo():
        return {
            'id': f'demo-sub-{uuid.uuid4().hex[:8]}',
            'demo': True,
            'submitters': [
                {'email': a.get('email'), 'slug': uuid.uuid4().hex[:10],
                 'embed_src': f'https://docuseal.demo/sign/{uuid.uuid4().hex[:10]}'}
                for a in approvers
            ],
        }
    resp = requests.post(
        f'{_base_url()}/submissions',
        headers=_headers(),
        json={
            'template_id': template_id,
            'send_email': send_email,
            'submitters': [
                {'role': 'Approver', 'name': a.get('name', ''), 'email': a['email'],
                 'phone': a.get('phone', ''), 'metadata': metadata or {}}
                for a in approvers
            ],
        },
        timeout=60,
    )
    if not resp.ok:
        raise DocuSealError(f'Submission create failed: {resp.status_code} {resp.text[:300]}')
    return resp.json()


def get_signed_document(submission_id) -> bytes | None:
    """Download the signed/audit-trailed PDF once all submitters complete."""
    if _demo():
        return None
    resp = requests.get(f'{_base_url()}/submissions/{submission_id}/documents',
                        headers=_headers(), timeout=60)
    if not resp.ok:
        raise DocuSealError(f'Document fetch failed: {resp.status_code}')
    docs = resp.json()
    if docs and docs[0].get('url'):
        return requests.get(docs[0]['url'], timeout=60).content
    return None
