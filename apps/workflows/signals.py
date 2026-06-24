import logging

logger = logging.getLogger(__name__)

# Module-level dicts track pre-save state for change detection.
# Keyed by str(pk) to survive serialization.
_candidate_previous_stage: dict = {}
_interview_previous_status: dict = {}
_leave_previous_status: dict = {}


def _fire(trigger_type: str, context: dict, company_id) -> None:
    from .engine import WorkflowEngine
    try:
        WorkflowEngine.fire(trigger_type, context, company_id)
    except Exception:
        logger.exception('WorkflowEngine.fire failed for trigger %s', trigger_type)


# ── Candidate ─────────────────────────────────────────────────────────────────

def candidate_pre_save(sender, instance, **kwargs):
    if not instance.pk:
        return
    try:
        old = sender.objects.get(pk=instance.pk)
        _candidate_previous_stage[str(instance.pk)] = old.current_stage
    except sender.DoesNotExist:
        pass


def candidate_post_save(sender, instance, created, **kwargs):
    company_id = instance.company_id
    if not company_id:
        return

    job_posting = None
    try:
        if instance.job_posting_id:
            job_posting = instance.job_posting
    except Exception:
        pass

    base_ctx = {
        'id': str(instance.id),
        'candidate_id': str(instance.id),
        'candidate_name': instance.full_name,
        'candidate_email': instance.email,
        'candidate_phone': instance.phone or '',
        'candidate_current_stage': instance.current_stage,
        'candidate_ai_score': str(instance.ai_score) if instance.ai_score is not None else '',
        'candidate_source': instance.source,
        'job_posting_id': str(instance.job_posting_id) if instance.job_posting_id else '',
        'job_posting_title': job_posting.title if job_posting else '',
        'job_posting_department': job_posting.department if job_posting else '',
        'company_id': str(company_id),
    }

    if created:
        _fire('candidate_applied', base_ctx, company_id)
    else:
        prev = _candidate_previous_stage.pop(str(instance.pk), None)
        if prev and prev != instance.current_stage:
            _fire('candidate_stage_changed', {**base_ctx, 'candidate_previous_stage': prev}, company_id)


# ── Interview ─────────────────────────────────────────────────────────────────

def interview_pre_save(sender, instance, **kwargs):
    if not instance.pk:
        return
    try:
        old = sender.objects.get(pk=instance.pk)
        _interview_previous_status[str(instance.pk)] = old.status
    except sender.DoesNotExist:
        pass


def interview_post_save(sender, instance, created, **kwargs):
    company_id = instance.company_id
    if not company_id:
        return

    prev = _interview_previous_status.pop(str(instance.pk), None)
    if created or instance.status != 'completed' or prev == 'completed':
        return

    candidate = None
    try:
        candidate = instance.candidate
    except Exception:
        pass
    job_posting = None
    try:
        if instance.job_posting_id:
            job_posting = instance.job_posting
    except Exception:
        pass

    context = {
        'id': str(instance.id),
        'interview_id': str(instance.id),
        'interview_type': instance.interview_type,
        'interview_status': instance.status,
        'interview_feedback_score': str(instance.feedback_score) if instance.feedback_score is not None else '',
        'interview_notes': instance.notes or '',
        'candidate_id': str(instance.candidate_id),
        'candidate_name': candidate.full_name if candidate else '',
        'candidate_email': candidate.email if candidate else '',
        'job_posting_id': str(instance.job_posting_id) if instance.job_posting_id else '',
        'job_posting_title': job_posting.title if job_posting else '',
        'company_id': str(company_id),
    }
    _fire('interview_completed', context, company_id)


# ── Leave ─────────────────────────────────────────────────────────────────────

def leave_pre_save(sender, instance, **kwargs):
    if not instance.pk:
        return
    try:
        old = sender.objects.get(pk=instance.pk)
        _leave_previous_status[str(instance.pk)] = old.status
    except sender.DoesNotExist:
        pass


def leave_post_save(sender, instance, created, **kwargs):
    company_id = instance.company_id
    if not company_id:
        return

    context = {
        'id': str(instance.id),
        'leave_id': str(instance.id),
        'leave_type': instance.leave_type,
        'leave_status': instance.status,
        'employee_id': str(instance.employee_id),
        'start_date': str(instance.start_date),
        'end_date': str(instance.end_date),
        'days_requested': str(instance.days_requested),
        'reason': instance.reason or '',
        'company_id': str(company_id),
    }

    if created:
        _fire('leave_submitted', context, company_id)
        return

    prev = _leave_previous_status.pop(str(instance.pk), None)
    if prev and prev != instance.status:
        if instance.status == 'approved':
            _fire('leave_approved', context, company_id)
        elif instance.status == 'rejected':
            _fire('leave_rejected', context, company_id)


# ── Employee ──────────────────────────────────────────────────────────────────

def employee_profile_post_save(sender, instance, created, **kwargs):
    if not created:
        return
    company_id = instance.company_id  # UUID FK value (Company.id is UUID PK)
    if not company_id:
        return
    context = {
        'id': str(instance.id),
        'employee_id': str(instance.id),
        'employee_number': instance.employee_number,
        'job_title': instance.job_title,
        'employment_type': instance.employment_type,
        'start_date': str(instance.start_date),
        'company_id': str(company_id),
    }
    _fire('employee_created', context, company_id)


# ── Exit ──────────────────────────────────────────────────────────────────────

def employee_exit_post_save(sender, instance, created, **kwargs):
    if not created:
        return
    company_id = instance.company_id
    if not company_id:
        return
    context = {
        'id': str(instance.id),
        'exit_id': str(instance.id),
        'exit_kind': instance.kind,
        'exit_status': instance.status,
        'exit_reason': instance.reason or '',
        'employee_id': str(instance.employee_id),
        'notice_date': str(instance.notice_date) if instance.notice_date else '',
        'last_working_day': str(instance.last_working_day) if instance.last_working_day else '',
        'company_id': str(company_id),
    }
    _fire('exit_process_started', context, company_id)
