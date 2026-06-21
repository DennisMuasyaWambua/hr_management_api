"""
Payroll approvals, documents, DocuSeal webhook, and the share-to-email API.
All endpoints are NEW — nothing in views.py changes.
"""
from django.http import FileResponse
from drf_spectacular.utils import (OpenApiParameter, OpenApiResponse,
                                   extend_schema)
from rest_framework import serializers as drf_serializers
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.models import ServiceAuditLog
from apps.core.permissions import (PayrollHROnly, request_company_id,
                                   request_user_id)
from apps.core.services import notifications as notif

from . import approval_service
from .approval_models import (ApproverConfig, PayrollApproval, PayrollApprover,
                              PayrollDocument)
from .models import PayrollRun
from .serializers_approvals import (ApproverConfigSerializer,
                                    PayrollApprovalSerializer,
                                    PayrollDocumentSerializer,
                                    ShareRequestSerializer)


class ApproverConfigViewSet(viewsets.ModelViewSet):
    """Dynamic approver configuration: M of N per company."""
    serializer_class = ApproverConfigSerializer
    permission_classes = [PayrollHROnly]

    def get_queryset(self):
        qs = ApproverConfig.objects.prefetch_related('approvers')
        company_id = request_company_id(self.request)
        if company_id:
            qs = qs.filter(company_id=company_id)
        return qs

    def perform_create(self, serializer):
        instance = serializer.save()
        if instance.required_approvals > instance.approvers.count() \
                and instance.approvers.exists():
            instance.required_approvals = instance.approvers.count()
            instance.save(update_fields=['required_approvals'])
        ServiceAuditLog.log('payroll.approver_config_created', request=self.request,
                            object_type='ApproverConfig', object_id=str(instance.id),
                            company_id=instance.company_id)


class PayrollApprovalViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PayrollApprovalSerializer
    permission_classes = [PayrollHROnly]

    def get_queryset(self):
        qs = PayrollApproval.objects.all()
        run_id = self.request.query_params.get('payroll_run_id')
        if run_id:
            qs = qs.filter(payroll_run_id=run_id)
        company_id = request_company_id(self.request)
        if company_id:
            qs = qs.filter(company_id=company_id)
        return qs


class PayrollWorkflowView(APIView):
    """
    POST api/payroll-workflow/{run_id}/{verb}/
    verbs: submit (→pending_approval, generates docs, notifies approvers),
           approve (records caller's approval; quorum → approved),
           reject, mark-paid (→paid + lock documents).
    """
    permission_classes = [PayrollHROnly]

    @extend_schema(
        summary='Drive the payroll approval lifecycle',
        description='Verbs: `submit` (draft/calculated → pending_approval; '
                    'generates password-protected PDF + color Excel, opens the '
                    'DocuSeal submission, notifies every configured approver '
                    'via email + SMS one-tap link, runs the minimum-wage '
                    'compliance check), `approve`/`reject` (records the '
                    'caller\'s signed decision — requires X-User-Id; M-of-N '
                    'quorum flips the run to approved), `mark-paid` (terminal; '
                    'locks all documents immutably).',
        parameters=[OpenApiParameter('verb', str, 'path',
                                     enum=['submit', 'approve', 'reject', 'mark-paid'])],
        request=None,
        responses={200: OpenApiResponse(description='Workflow result'),
                   409: OpenApiResponse(description='Invalid state transition')},
    )
    def post(self, request, run_id, verb):
        try:
            run = PayrollRun.objects.get(id=run_id)
        except PayrollRun.DoesNotExist:
            return Response({'error': 'Payroll run not found'},
                            status=status.HTTP_404_NOT_FOUND)
        user_id = request_user_id(request)

        if verb == 'submit':
            try:
                from .document_service import run_minimum_wage_check
                wage_alerts = run_minimum_wage_check(run)
                result = approval_service.submit_for_approval(
                    run, triggered_by=user_id, request=request)
                result['minimum_wage_alerts'] = len(wage_alerts)
                return Response(result)
            except approval_service.ApprovalError as exc:
                return Response({'error': str(exc)},
                                status=status.HTTP_409_CONFLICT)

        if verb in ('approve', 'reject'):
            if not user_id:
                return Response({'error': 'X-User-Id header required to sign'},
                                status=status.HTTP_400_BAD_REQUEST)
            result = approval_service.record_approval(
                run.id, user_id, via='dashboard',
                decision='approved' if verb == 'approve' else 'rejected',
                comment=request.data.get('comment', ''), request=request)
            code = status.HTTP_409_CONFLICT if 'error' in result else status.HTTP_200_OK
            return Response(result, status=code)

        if verb == 'mark-paid':
            if run.status not in ('approved', 'processing', 'completed'):
                return Response({'error': f'Cannot mark {run.status} run as paid; '
                                          'quorum approval required first.'},
                                status=status.HTTP_409_CONFLICT)
            run.status = 'paid'
            run.save(update_fields=['status', 'updated_at'])
            locked = approval_service.lock_documents(run)
            ServiceAuditLog.log('payroll.marked_paid', request=request,
                                object_type='PayrollRun', object_id=str(run.id),
                                company_id=run.company_id, actor_user_id=user_id,
                                metadata={'documents_locked': locked})
            return Response({'status': 'paid', 'documents_locked': locked})

        return Response({'error': f'Unknown verb {verb}'},
                        status=status.HTTP_400_BAD_REQUEST)


class PayrollDocumentViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PayrollDocumentSerializer
    permission_classes = [PayrollHROnly]

    def get_queryset(self):
        qs = PayrollDocument.objects.all()
        run_id = self.request.query_params.get('payroll_run_id')
        if run_id:
            qs = qs.filter(payroll_run_id=run_id)
        company_id = request_company_id(self.request)
        if company_id:
            qs = qs.filter(company_id=company_id)
        return qs

    @action(detail=False, methods=['post'])
    def generate(self, request):
        """Generate (or regenerate) PDF+Excel for a run. Body: {"payroll_run_id": ...}"""
        try:
            run = PayrollRun.objects.get(id=request.data.get('payroll_run_id'))
        except PayrollRun.DoesNotExist:
            return Response({'error': 'Payroll run not found'},
                            status=status.HTTP_404_NOT_FOUND)
        from .document_service import generate_run_documents
        try:
            doc = generate_run_documents(run,
                                         triggered_by=request_user_id(request))
        except PermissionError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(PayrollDocumentSerializer(doc).data,
                        status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'])
    def download(self, request, pk=None):
        doc = self.get_object()
        ServiceAuditLog.log('payroll.document_downloaded', request=request,
                            object_type='PayrollDocument', object_id=str(doc.id),
                            company_id=doc.company_id)
        return FileResponse(doc.file.open('rb'), as_attachment=True,
                            filename=doc.file.name.rsplit('/', 1)[-1])


class DocuSealWebhook(APIView):
    """
    DocuSeal calls this on submitter completion (form.completed). We map the
    signature back to a payroll approval via metadata.payroll_run_id + email.
    Configure in DocuSeal: webhook URL {API}/api/docuseal/webhook/.
    """
    authentication_classes = []
    permission_classes = []

    @extend_schema(
        summary='DocuSeal signature webhook',
        description='Configure in DocuSeal with events form.completed / '
                    'submission.completed. Optionally guarded by '
                    'X-Docuseal-Signature matching DOCUSEAL_WEBHOOK_SECRET. '
                    'Maps the signer back to a payroll approval via '
                    'metadata.payroll_run_id + submitter email.',
        request=None,
        responses={200: OpenApiResponse(description='Approval recorded or event ignored')},
    )
    def post(self, request):
        from django.conf import settings
        secret = getattr(settings, 'DOCUSEAL_WEBHOOK_SECRET', '')
        if secret and request.headers.get('X-Docuseal-Signature') != secret:
            return Response(status=status.HTTP_403_FORBIDDEN)

        payload = request.data or {}
        event = payload.get('event_type', '')
        data = payload.get('data', {})
        if event not in ('form.completed', 'submission.completed'):
            return Response({'ok': True, 'ignored': event})

        metadata = data.get('metadata') or {}

        # Background-check validation submissions route back to apps.hr.
        bg_id = metadata.get('background_check_id')
        if bg_id:
            return self._handle_background_check(bg_id, data, request)

        run_id = metadata.get('payroll_run_id')
        email = data.get('email', '')
        if not run_id:
            sub_id = str(data.get('submission_id', data.get('id', '')))
            doc = PayrollDocument.objects.filter(
                docuseal_submission_id=sub_id).first()
            run_id = str(doc.payroll_run_id) if doc else None
        if not run_id:
            return Response({'error': 'cannot resolve payroll run'},
                            status=status.HTTP_400_BAD_REQUEST)

        approver = PayrollApprover.objects.filter(email__iexact=email,
                                                  is_active=True).first()
        if approver is None:
            return Response({'error': f'no approver with email {email}'},
                            status=status.HTTP_400_BAD_REQUEST)
        result = approval_service.record_approval(
            run_id, approver.user_id, via='docuseal',
            docuseal_slug=str(data.get('slug', '')), request=request)
        return Response({'ok': True, 'result': result})

    @staticmethod
    def _extract_values(data) -> dict:
        """Flatten DocuSeal completed `values` into {field_name: value}."""
        values = data.get('values') or data.get('fields') or []
        out = {}
        if isinstance(values, dict):
            return values
        for item in values:
            if isinstance(item, dict):
                name = item.get('field') or item.get('name')
                if name is not None:
                    out[name] = item.get('value')
        return out

    def _handle_background_check(self, bg_id, data, request):
        from apps.hr.background_check_service import record_validation_result
        from apps.hr.models import BackgroundCheck
        from apps.core.services import docuseal

        check = BackgroundCheck.objects.filter(id=bg_id, is_deleted=False).first()
        if check is None:
            return Response({'error': f'no background check {bg_id}'},
                            status=status.HTTP_400_BAD_REQUEST)

        values = self._extract_values(data)
        clean_val = values.get('Subject is clean')
        is_clean = str(clean_val).strip().lower() in ('true', '1', 'yes', 'on', 'checked')
        comments = str(values.get('Comments') or '')

        signed_url = ''
        try:
            sub_id = check.docuseal_submission_id or str(data.get('submission_id', data.get('id', '')))
            signed = docuseal.get_signed_document(sub_id) if sub_id else None
            if signed:
                # store URL-less marker; the bytes can be persisted by a future
                # documents pipeline. We at least record that a signed copy exists.
                signed_url = f'docuseal:submission/{sub_id}'
        except Exception:  # noqa: BLE001
            signed_url = ''

        result = record_validation_result(
            check, is_clean=is_clean, comments=comments,
            signed_url=signed_url, request=request)
        return Response({'ok': True, 'result': result})


class ShareView(APIView):
    """
    Share button backend (01-Jun session): auto-generate the artifact and email
    it pre-templated — no manual download/upload.
    Body: {module: 'payroll', object_id, format: 'pdf'|'excel',
           recipients: ['a@b.com', ...], message?, document_title?}
    """
    permission_classes = [PayrollHROnly]

    @extend_schema(
        summary='Share a document by email (auto-generate + attach)',
        request=ShareRequestSerializer,
        responses={200: OpenApiResponse(
            description='{"sent": [{"recipient", "status"}]}')},
    )
    def post(self, request):
        module = request.data.get('module', 'payroll')
        recipients = request.data.get('recipients', [])
        if not recipients:
            return Response({'error': 'recipients required'},
                            status=status.HTTP_400_BAD_REQUEST)

        if module == 'payroll':
            attachment = self._payroll_attachment(request)
            if isinstance(attachment, Response):
                return attachment
        else:
            return Response({'error': f'module {module} not yet shareable; '
                                      'payroll only for now'},
                            status=status.HTTP_400_BAD_REQUEST)

        filename, content, mimetype, company_id = attachment
        title = request.data.get('document_title', filename)
        from .models import Company
        company = Company.objects.filter(id=company_id).first()
        sent = []
        for email in recipients:
            log = notif.send_email(
                email,
                f'{title} from {company.name if company else "Sheer Logic HR"}',
                request.data.get('message',
                                 'Please find the attached document.'),
                attachments=[(filename, content, mimetype)],
                event='share.document', company_id=company_id,
                source_app='dashboard', related=('share', filename))
            sent.append({'recipient': email, 'status': log.status})
        ServiceAuditLog.log('share.sent', request=request,
                            object_type=module, company_id=company_id,
                            object_id=str(request.data.get('object_id', '')),
                            metadata={'recipients': recipients, 'file': filename})
        return Response({'sent': sent})

    def _payroll_attachment(self, request):
        fmt = request.data.get('format', 'pdf')
        try:
            run = PayrollRun.objects.get(id=request.data.get('object_id'))
        except PayrollRun.DoesNotExist:
            return Response({'error': 'Payroll run not found'},
                            status=status.HTTP_404_NOT_FOUND)
        doc_type = 'payroll_pdf' if fmt == 'pdf' else 'payroll_excel'
        doc = PayrollDocument.objects.filter(payroll_run_id=run.id,
                                             doc_type=doc_type).first()
        if doc is None:
            from .document_service import generate_run_documents
            generate_run_documents(run, triggered_by=request_user_id(request))
            doc = PayrollDocument.objects.filter(payroll_run_id=run.id,
                                                 doc_type=doc_type).first()
        with doc.file.open('rb') as fh:
            content = fh.read()
        filename = doc.file.name.rsplit('/', 1)[-1]
        mimetype = 'application/pdf' if fmt == 'pdf' else \
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        return filename, content, mimetype, run.company_id
