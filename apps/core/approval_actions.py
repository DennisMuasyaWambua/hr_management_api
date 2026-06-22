"""
Dispatch table for one-tap approval tokens. Each handler executes the
domain-side effect and returns a short result dict for the audit log.
"""


def execute_one_tap_action(token, request):
    action = token.action

    if action in ('overtime.approve', 'overtime.reject'):
        from apps.hr.models import OvertimeRequest
        try:
            ot = OvertimeRequest.objects.get(id=token.object_id)
        except OvertimeRequest.DoesNotExist:
            return {'error': 'overtime request not found'}
        if ot.status != 'pending':
            return {'error': f'already {ot.status}'}
        ot.decide('approved' if action.endswith('approve') else 'rejected',
                  approver_user_id=token.approver_user_id)
        return {'status': ot.status}

    if action == 'leave_recall.approve':
        from apps.hr.models import LeaveRecall
        try:
            recall = LeaveRecall.objects.get(id=token.object_id)
        except LeaveRecall.DoesNotExist:
            return {'error': 'recall not found'}
        if recall.status != 'pending':
            return {'error': f'already {recall.status}'}
        recall.approve(approver_user_id=token.approver_user_id)
        return {'status': recall.status}

    if action in ('leave.approve', 'leave.reject'):
        # Leave rows live in Supabase; record the decision server-side and let
        # the dashboard's Supabase sync apply it (webhook-style row in audit).
        return {'status': 'recorded',
                'note': 'leave decision recorded; dashboard applies to Supabase leaves table'}

    if action == 'payroll.approve':
        from apps.payroll.approval_service import record_approval
        signature = ''
        data = getattr(request, 'data', None) if request is not None else None
        if isinstance(data, dict):
            signature = data.get('signature', '') or ''
        return record_approval(payroll_run_id=token.object_id,
                               approver_user_id=token.approver_user_id,
                               via='one_tap', signature_image=signature,
                               request=request)

    return {'error': f'unknown action {action}'}
