import logging

logger = logging.getLogger(__name__)


class ExecutorRegistry:
    _registry: dict = {}

    @classmethod
    def register(cls, action_type: str):
        def decorator(executor_cls):
            cls._registry[action_type] = executor_cls()
            return executor_cls
        return decorator

    @classmethod
    def get(cls, action_type: str):
        return cls._registry.get(action_type)


def _render(template: str, context: dict) -> str:
    """Substitute {{key}} placeholders from context."""
    result = template
    for key, value in context.items():
        result = result.replace(f'{{{{{key}}}}}', str(value) if value is not None else '')
    return result


@ExecutorRegistry.register('send_notification')
class SendNotificationExecutor:
    def execute(self, params: dict, context: dict, execution) -> str:
        from apps.core.services.notifications import notify
        event = params.get('event', 'workflow.notification')
        recipients = params.get('recipients', [])
        if not recipients:
            return 'No recipients specified — skipped'
        notify(
            event,
            recipients,
            context=context,
            company_id=str(execution.company_id),
            source_app='workflows',
        )
        return f'Notification sent to {len(recipients)} recipient(s)'


@ExecutorRegistry.register('send_email')
class SendEmailExecutor:
    def execute(self, params: dict, context: dict, execution) -> str:
        from apps.core.services.notifications import send_email
        recipient = _render(params.get('recipient', ''), context)
        subject = _render(params.get('subject', 'Workflow Notification'), context)
        body = _render(params.get('body', ''), context)
        if not recipient:
            return 'No recipient email specified — skipped'
        send_email(
            recipient, subject, body,
            event='workflow.email',
            company_id=str(execution.company_id),
            source_app='workflows',
        )
        return f'Email sent to {recipient}'


@ExecutorRegistry.register('create_task')
class CreateTaskExecutor:
    def execute(self, params: dict, context: dict, execution) -> str:
        from .models import WorkflowTask
        title = _render(params.get('title', 'Workflow Task'), context)
        description = _render(params.get('description', ''), context)
        WorkflowTask.objects.create(
            execution=execution,
            title=title,
            description=description,
            assigned_to=params.get('assigned_to') or None,
            priority=params.get('priority', 'normal'),
            source_module=params.get('source_module', 'workflows'),
            source_record_id=execution.source_object_id,
            company_id=execution.company_id,
            tenant_id=execution.tenant_id,
        )
        return f'Task created: {title}'


@ExecutorRegistry.register('create_action_item')
class CreateActionItemExecutor:
    def execute(self, params: dict, context: dict, execution) -> str:
        from .models import WorkflowTask
        title = _render(params.get('title', 'Action Required'), context)
        description = _render(params.get('description', ''), context)
        WorkflowTask.objects.create(
            execution=execution,
            title=title,
            description=description,
            priority=params.get('priority', 'high'),
            source_module=params.get('source_module', 'workflows'),
            source_record_id=execution.source_object_id,
            company_id=execution.company_id,
            tenant_id=execution.tenant_id,
        )
        return f'Action item created: {title}'


@ExecutorRegistry.register('assign_recruiter')
class AssignRecruiterExecutor:
    def execute(self, params: dict, context: dict, execution) -> str:
        from apps.recruitment.models import Candidate
        candidate_id = params.get('candidate_id') or context.get('candidate_id')
        recruiter_id = params.get('recruiter_id')
        if not candidate_id or not recruiter_id:
            return 'Missing candidate_id or recruiter_id — skipped'
        updated = Candidate.objects.filter(id=candidate_id).update(recruiter_id=recruiter_id)
        if updated:
            return f'Recruiter {recruiter_id} assigned to candidate {candidate_id}'
        return f'Candidate {candidate_id} not found'


@ExecutorRegistry.register('assign_manager')
class AssignManagerExecutor:
    def execute(self, params: dict, context: dict, execution) -> str:
        from apps.payroll.models import EmployeeProfile
        employee_id = params.get('employee_id') or context.get('employee_id')
        manager_id = params.get('manager_id')
        if not employee_id or not manager_id:
            return 'Missing employee_id or manager_id — skipped'
        updated = EmployeeProfile.objects.filter(id=employee_id).update(manager_id=manager_id)
        if updated:
            return f'Manager {manager_id} assigned to employee {employee_id}'
        return f'Employee {employee_id} not found'


@ExecutorRegistry.register('schedule_interview')
class ScheduleInterviewExecutor:
    def execute(self, params: dict, context: dict, execution) -> str:
        from datetime import timedelta
        from django.utils import timezone
        from apps.recruitment.models import Interview
        candidate_id = params.get('candidate_id') or context.get('candidate_id')
        job_posting_id = params.get('job_posting_id') or context.get('job_posting_id')
        if not candidate_id or not job_posting_id:
            return 'Missing candidate_id or job_posting_id — skipped'
        offset_days = int(params.get('scheduled_at_offset_days', 7))
        scheduled_at = timezone.now() + timedelta(days=offset_days)
        interview = Interview.objects.create(
            candidate_id=candidate_id,
            job_posting_id=job_posting_id,
            interview_type=params.get('interview_type', 'l1'),
            status='scheduled',
            scheduled_at=scheduled_at,
            location=params.get('location', ''),
            company_id=execution.company_id,
            tenant_id=execution.tenant_id,
        )
        return f'Interview {interview.id} scheduled for {scheduled_at.date()}'


@ExecutorRegistry.register('escalate_approval')
class EscalateApprovalExecutor:
    def execute(self, params: dict, context: dict, execution) -> str:
        from apps.core.services.notifications import notify
        recipients = params.get('recipients', [])
        note = _render(params.get('note', 'Escalation required'), context)
        if not recipients:
            return 'No escalation recipients specified — skipped'
        notify(
            'action.escalated',
            recipients,
            context={**context, 'note': note},
            company_id=str(execution.company_id),
            source_app='workflows',
        )
        return f'Escalation sent to {len(recipients)} recipient(s)'
