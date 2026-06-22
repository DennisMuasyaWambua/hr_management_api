"""
Core API: RBAC management (frontend autonomy), notifications, one-tap
approvals, audit log access.
"""
from django.http import HttpResponse
from django.utils import timezone
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (AppUser, NotificationLog, NotificationTemplate,
                     OneTapToken, Permission, Role, RolePermission,
                     ServiceAuditLog, StaffAssignment, UserRoleAssignment)
from .permissions import (HasModulePermission, IsHighestRank,
                          request_company_id, request_user_id)
from .serializers import (AppUserSerializer, NotificationLogSerializer,
                          NotificationTemplateSerializer, PermissionSerializer,
                          RolePermissionSerializer, RoleSerializer,
                          SendNotificationSerializer,
                          ServiceAuditLogSerializer,
                          StaffAssignmentSerializer,
                          UserRoleAssignmentSerializer)
from .services import notifications as notif


def _scope_company(qs, request):
    company_id = request_company_id(request)
    if company_id:
        from django.db.models import Q
        return qs.filter(Q(company_id=company_id) | Q(company_id__isnull=True))
    return qs


class AppUserViewSet(viewsets.ModelViewSet):
    """User directory (HR admins, managers, employees) — replaces direct
    Supabase queries against the old `users` table. Only role/is_active are
    editable from the dashboard; identity fields are managed by login."""
    serializer_class = AppUserSerializer
    permission_classes = [IsHighestRank]
    http_method_names = ['get', 'put', 'patch', 'head', 'options']

    def get_queryset(self):
        qs = AppUser.objects.filter(is_deleted=False)
        company_id = (self.request.query_params.get('companyId') or
                     self.request.query_params.get('company_id'))
        if company_id:
            qs = qs.filter(company_id=company_id)
        return qs.order_by('full_name')


class RoleViewSet(viewsets.ModelViewSet):
    """Roles + their grants. Mutations restricted to the highest rank."""
    serializer_class = RoleSerializer
    permission_classes = [IsHighestRank]
    rbac_module = 'rbac'

    def get_queryset(self):
        return _scope_company(Role.objects.all().prefetch_related('grants__permission'),
                              self.request)

    @action(detail=True, methods=['post'])
    def grant(self, request, pk=None):
        """Grant permission codenames to this role. Body: {"codenames": [...]}"""
        role = self.get_object()
        codenames = request.data.get('codenames', [])
        granted = []
        for codename in codenames:
            try:
                perm = Permission.objects.get(codename=codename)
            except Permission.DoesNotExist:
                return Response({'error': f'Unknown permission: {codename}'},
                                status=status.HTTP_400_BAD_REQUEST)
            _, created = RolePermission.objects.get_or_create(
                role=role, permission=perm,
                defaults={'granted_by': request_user_id(request)})
            if created:
                granted.append(codename)
        ServiceAuditLog.log('rbac.grant', request=request,
                            object_type='role', object_id=str(role.id),
                            company_id=role.company_id,
                            metadata={'granted': granted, 'requested': codenames})
        return Response(RoleSerializer(role).data)

    @action(detail=True, methods=['post'])
    def revoke(self, request, pk=None):
        """Revoke permission codenames from this role. Body: {"codenames": [...]}"""
        role = self.get_object()
        codenames = request.data.get('codenames', [])
        deleted, _ = RolePermission.objects.filter(
            role=role, permission__codename__in=codenames).delete()
        ServiceAuditLog.log('rbac.revoke', request=request,
                            object_type='role', object_id=str(role.id),
                            company_id=role.company_id,
                            metadata={'revoked': codenames, 'count': deleted})
        return Response(RoleSerializer(role).data)


class PermissionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Permission.objects.all()
    serializer_class = PermissionSerializer
    rbac_module = 'rbac'
    permission_classes = [HasModulePermission]
    pagination_class = None


class UserRoleAssignmentViewSet(viewsets.ModelViewSet):
    serializer_class = UserRoleAssignmentSerializer
    permission_classes = [IsHighestRank]
    rbac_module = 'rbac'

    def get_queryset(self):
        qs = UserRoleAssignment.objects.select_related('role')
        company_id = request_company_id(self.request)
        if company_id:
            qs = qs.filter(company_id=company_id)
        user_id = self.request.query_params.get('user_id')
        if user_id:
            qs = qs.filter(user_id=user_id)
        return qs

    def perform_create(self, serializer):
        instance = serializer.save(assigned_by=request_user_id(self.request))
        ServiceAuditLog.log('rbac.assign_role', request=self.request,
                            object_type='user', object_id=str(instance.user_id),
                            company_id=instance.company_id,
                            metadata={'role': instance.role.slug})

    def perform_destroy(self, instance):
        ServiceAuditLog.log('rbac.unassign_role', request=self.request,
                            object_type='user', object_id=str(instance.user_id),
                            company_id=instance.company_id,
                            metadata={'role': instance.role.slug})
        instance.delete()


class StaffAssignmentViewSet(viewsets.ModelViewSet):
    """
    Assign employees to a deployed HR / Manager (who then only sees those
    employees). Managed by the highest-ranked role in scope (super_admin /
    company_admin). Filter with ?staff_user_id= or ?company_id=.
    """
    serializer_class = StaffAssignmentSerializer
    permission_classes = [IsHighestRank]
    rbac_module = 'rbac'

    def get_queryset(self):
        qs = StaffAssignment.objects.all()
        company_id = request_company_id(self.request)
        if company_id:
            qs = qs.filter(company_id=company_id)
        staff_user_id = self.request.query_params.get('staff_user_id')
        if staff_user_id:
            qs = qs.filter(staff_user_id=staff_user_id)
        return qs

    def perform_create(self, serializer):
        instance = serializer.save(assigned_by=request_user_id(self.request))
        ServiceAuditLog.log('rbac.staff_assigned', request=self.request,
                            object_type='employee', object_id=str(instance.employee_id),
                            company_id=instance.company_id,
                            metadata={'staff_user_id': str(instance.staff_user_id)})

    def perform_destroy(self, instance):
        ServiceAuditLog.log('rbac.staff_unassigned', request=self.request,
                            object_type='employee', object_id=str(instance.employee_id),
                            company_id=instance.company_id,
                            metadata={'staff_user_id': str(instance.staff_user_id)})
        instance.delete()


class NotificationTemplateViewSet(viewsets.ModelViewSet):
    serializer_class = NotificationTemplateSerializer
    permission_classes = [HasModulePermission]
    rbac_module = 'notifications'

    def get_queryset(self):
        return _scope_company(NotificationTemplate.objects.all(), self.request)


class NotificationViewSet(viewsets.GenericViewSet):
    """Unified send + delivery log for all three frontends."""
    permission_classes = [HasModulePermission]
    rbac_module = 'notifications'
    queryset = NotificationLog.objects.all()
    serializer_class = NotificationLogSerializer

    @action(detail=False, methods=['post'])
    def send(self, request):
        ser = SendNotificationSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        if d['event']:
            log_ids = notif.notify(
                d['event'], d['recipients'], d['context'],
                channels=d['channels'], company_id=d.get('company_id'),
                source_app=d['source_app'])
        else:
            # Ad-hoc message (no template event)
            log_ids = []
            for channel in d['channels']:
                for r in d['recipients']:
                    addr = r.get('email') if channel == 'email' else r.get('phone')
                    if not addr:
                        continue
                    if channel == 'email':
                        log = notif.send_email(addr, d['subject'] or 'Notification',
                                               d['message'],
                                               company_id=d.get('company_id'),
                                               source_app=d['source_app'])
                    else:
                        log = notif.SENDERS[channel](addr, d['message'],
                                                     company_id=d.get('company_id'),
                                                     source_app=d['source_app'])
                    log_ids.append(str(log.id))
        return Response({'queued': log_ids}, status=status.HTTP_202_ACCEPTED)

    @action(detail=False, methods=['get'])
    def logs(self, request):
        qs = self.get_queryset()
        company_id = request_company_id(request)
        if company_id:
            qs = qs.filter(company_id=company_id)
        page = self.paginate_queryset(qs)
        return self.get_paginated_response(
            NotificationLogSerializer(page, many=True).data)


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ServiceAuditLogSerializer
    permission_classes = [HasModulePermission]
    rbac_module = 'audit'

    def get_queryset(self):
        qs = ServiceAuditLog.objects.all()
        company_id = request_company_id(self.request)
        if company_id:
            qs = qs.filter(company_id=company_id)
        action_filter = self.request.query_params.get('action')
        if action_filter:
            qs = qs.filter(action__startswith=action_filter)
        return qs


class OneTapApprovalView(APIView):
    """
    Tokenized one-tap approval target for links sent over SMS/WhatsApp/email.
    GET returns what would be approved; POST executes. No session required —
    possession of the unexpired single-use token is the credential.
    """
    authentication_classes = []  # token IS the auth
    permission_classes = []

    def _get_token(self, token):
        try:
            return OneTapToken.objects.get(token=token)
        except OneTapToken.DoesNotExist:
            return None

    @staticmethod
    def _payroll_detail_html(token):
        """Employee table (with deduction breakdown) shown on the approval page."""
        try:
            from apps.payroll.approval_service import _EMAIL_COLS, _employee_rows
            from apps.payroll.models import Company, PayrollRun
            run = PayrollRun.objects.get(id=token.object_id)
        except Exception:  # noqa: BLE001 — page must still render if lookup fails
            return ''
        rows, count, totals = _employee_rows(run)
        company = Company.objects.filter(id=run.company_id).first()
        company_name = company.name if company else ''
        head = ''.join(
            f'<th class="{"r" if align == "right" else ""}">{label}</th>'
            for _k, label, align in _EMAIL_COLS)
        totals_cells = ''.join(
            ('<td><strong>Totals</strong></td>' if key == 'name' else
             ('<td></td>' if key == 'role' else
              f'<td class="r"><strong>KES {totals[key]:,.2f}</strong></td>'))
            for key, _h, _a in _EMAIL_COLS)
        return (
            f'<div class="info" style="background:#f8fafc;border-color:#e2e8f0">'
            f'<p style="color:#1e293b"><strong>{company_name}</strong> — '
            f'Payroll {run.period_display} ({count} employee'
            f'{"s" if count != 1 else ""})</p></div>'
            f'<div style="overflow-x:auto"><table><tr>{head}</tr>{rows}'
            f'<tr style="background:#f8fafc">{totals_cells}</tr></table></div>'
            f'<p style="font-size:12px;color:#64748b;text-align:left">'
            f'Total deductions: KES {totals["deductions"]:,.2f} '
            f'(PAYE + NSSF + NHIF + HELB)</p>')

    @extend_schema(
        summary='Inspect a one-tap approval token',
        request=None,
        responses={200: OpenApiResponse(description='{"valid", "action", "object_id", "expires_at"}'),
                   404: OpenApiResponse(description='Token invalid, used or expired')},
    )
    def get(self, request, token):
        t = self._get_token(token)
        wants_html = 'text/html' in request.headers.get('Accept', '')

        if t is None or not t.is_valid:
            if wants_html:
                return HttpResponse(
                    '<html><body style="font-family:sans-serif;text-align:center;padding:60px">'
                    '<h2 style="color:#dc2626">&#10005; Link expired or already used</h2>'
                    '<p>This approval link has either been used or has expired.</p></body></html>',
                    status=404, content_type='text/html')
            return Response({'valid': False, 'error': 'Token invalid, used or expired'},
                            status=status.HTTP_404_NOT_FOUND)

        if wants_html:
            action_label = t.action.replace('_', ' ').replace('.', ' — ').title()
            expires = t.expires_at.strftime('%d %b %Y %H:%M') if t.expires_at else 'N/A'
            url = request.build_absolute_uri()
            needs_sig = t.action == 'payroll.approve'
            detail_html = self._payroll_detail_html(t) if needs_sig else ''
            sig_html = (
                '<p style="font-size:13px;color:#475569;text-align:left;margin:18px 0 6px">'
                '<strong>Draw your signature below to approve:</strong></p>'
                '<canvas id="sig" width="360" height="140" '
                'style="border:1px dashed #94a3b8;border-radius:8px;width:100%;'
                'touch-action:none;background:#fff;cursor:crosshair"></canvas>'
                '<div style="text-align:right;margin:4px 0 8px">'
                '<a href="#" id="clear" style="font-size:12px;color:#64748b">Clear</a></div>'
            ) if needs_sig else ''
            btn_label = '&#9997; Sign &amp; Approve' if needs_sig else '&#10003;&nbsp; Approve'
            js_needs_sig = 'true' if needs_sig else 'false'
            html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Payroll Approval</title>
  <style>
    body {{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
           background:#f8fafc;display:flex;align-items:center;justify-content:center;
           min-height:100vh;margin:0;padding:20px;}}
    .card {{background:#fff;border-radius:12px;box-shadow:0 4px 24px rgba(0,0,0,.1);
             padding:32px;max-width:480px;width:100%;text-align:center;}}
    h2 {{color:#1e293b;margin-bottom:6px;}}
    .badge {{display:inline-block;background:#dbeafe;color:#1d4ed8;border-radius:20px;
              padding:4px 14px;font-size:13px;font-weight:600;margin-bottom:20px;}}
    .info {{background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;
             padding:14px;margin:16px 0;text-align:left;font-size:14px;}}
    .info p {{margin:4px 0;color:#166534;}}
    table {{border-collapse:collapse;width:100%;font-size:13px;margin:8px 0;}}
    th,td {{padding:5px 8px;border-bottom:1px solid #eee;text-align:left;}}
    th {{background:#f1f5f9;}} td.r,th.r {{text-align:right;}}
    button {{background:#16a34a;color:#fff;border:none;width:100%;padding:14px;
              border-radius:8px;font-size:16px;font-weight:600;cursor:pointer;
              margin-top:8px;transition:background .2s;}}
    button:hover {{background:#15803d;}}
    button:disabled {{background:#9ca3af;cursor:not-allowed;}}
    .msg {{margin-top:16px;font-size:14px;display:none;}}
    .success {{color:#16a34a;}} .error {{color:#dc2626;}}
  </style>
</head>
<body>
  <div class="card">
    <div class="badge">Sheer Logic HR</div>
    <h2>&#128196; Payroll Approval</h2>
    <p style="color:#64748b;font-size:14px">You have been asked to review, sign and approve this payroll.</p>
    {detail_html}
    {sig_html}
    <p style="font-size:13px;color:#64748b">
      Approving records your signature. Disbursement is enabled once the required number of approvers have signed.
    </p>
    <button id="btn" onclick="doApprove()">{btn_label}</button>
    <div class="info" style="margin-top:18px">
      <p><strong>Action:</strong> {action_label}</p>
      <p><strong>Expires:</strong> {expires}</p>
    </div>
    <div class="msg success" id="ok">&#10003; Approved! Disbursement has been enabled.</div>
    <div class="msg error" id="err"></div>
  </div>
  <script>
    const NEEDS_SIG = {js_needs_sig};
    let sigCtx=null, drawing=false, hasInk=false;
    if (NEEDS_SIG) {{
      const c=document.getElementById('sig');
      sigCtx=c.getContext('2d'); sigCtx.lineWidth=2; sigCtx.lineCap='round'; sigCtx.strokeStyle='#1e293b';
      const pos=e=>{{const r=c.getBoundingClientRect();const t=e.touches?e.touches[0]:e;
        return {{x:(t.clientX-r.left)*(c.width/r.width), y:(t.clientY-r.top)*(c.height/r.height)}};}};
      const start=e=>{{drawing=true;const p=pos(e);sigCtx.beginPath();sigCtx.moveTo(p.x,p.y);e.preventDefault();}};
      const move=e=>{{if(!drawing)return;const p=pos(e);sigCtx.lineTo(p.x,p.y);sigCtx.stroke();hasInk=true;e.preventDefault();}};
      const end=()=>{{drawing=false;}};
      c.addEventListener('mousedown',start);c.addEventListener('mousemove',move);
      window.addEventListener('mouseup',end);
      c.addEventListener('touchstart',start);c.addEventListener('touchmove',move);
      c.addEventListener('touchend',end);
      document.getElementById('clear').addEventListener('click',ev=>{{
        ev.preventDefault();sigCtx.clearRect(0,0,c.width,c.height);hasInk=false;}});
    }}
    async function doApprove() {{
      const btn = document.getElementById('btn');
      const err = document.getElementById('err'); err.style.display='none';
      let signature='';
      if (NEEDS_SIG) {{
        if(!hasInk) {{ err.textContent='Please draw your signature first.'; err.style.display='block'; return; }}
        signature=document.getElementById('sig').toDataURL('image/png');
      }}
      btn.disabled = true; btn.textContent = 'Submitting…';
      try {{
        // Post to the page's own URL (https as loaded) — avoids mixed-content
        // when Railway's proxy makes the server build an http:// absolute URI.
        const r = await fetch(window.location.href, {{method:'POST',
          headers:{{'Content-Type':'application/json'}},
          body: JSON.stringify({{signature}})}});
        const d = await r.json();
        if (d.ok) {{
          btn.style.display='none';
          document.getElementById('ok').style.display='block';
        }} else {{
          btn.disabled=false; btn.innerHTML='{btn_label}';
          err.textContent=d.error||(d.result&&d.result.error)||'Something went wrong'; err.style.display='block';
        }}
      }} catch(ex) {{
        btn.disabled=false; btn.innerHTML='{btn_label}';
        err.textContent='Network error — please try again.'; err.style.display='block';
      }}
    }}
  </script>
</body>
</html>"""
            return HttpResponse(html, content_type='text/html')

        return Response({'valid': True, 'action': t.action, 'object_id': t.object_id,
                         'expires_at': t.expires_at})

    @extend_schema(
        summary='Execute a one-tap approval (single use)',
        description='The unexpired single-use token IS the credential — links '
                    'are sent to approvers over SMS/WhatsApp/email. Executes '
                    'exactly one predefined action (approve/reject overtime, '
                    'leave recall or payroll run) and burns the token.',
        request=None,
        responses={200: OpenApiResponse(description='{"ok", "action", "result"}'),
                   404: OpenApiResponse(description='Token invalid, used or expired')},
    )
    def post(self, request, token):
        t = self._get_token(token)
        if t is None or not t.is_valid:
            return Response({'error': 'Token invalid, used or expired'},
                            status=status.HTTP_404_NOT_FOUND)
        from apps.core.approval_actions import execute_one_tap_action
        result = execute_one_tap_action(t, request)
        t.used_at = timezone.now()
        t.save(update_fields=['used_at'])
        ServiceAuditLog.log(f'one_tap.{t.action}', request=request,
                            object_type=t.action.split('.')[0], object_id=t.object_id,
                            company_id=t.company_id,
                            actor_user_id=t.approver_user_id,
                            metadata={'result': result})
        return Response({'ok': True, 'action': t.action, 'result': result})
