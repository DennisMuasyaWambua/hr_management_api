from uuid import UUID

from django.utils import timezone

from apps.actions.dataclasses import ActionCategory, ActionItem, ActionPriority
from apps.actions.generators.base import BaseActionGenerator
from apps.actions.services import register_generator

_PRIORITY_MAP = {
    'urgent': ActionPriority.CRITICAL,
    'high': ActionPriority.HIGH,
    'normal': ActionPriority.MEDIUM,
    'low': ActionPriority.LOW,
}


@register_generator
class WorkflowTaskGenerator(BaseActionGenerator):
    """Surfaces open WorkflowTasks in the Action Center."""
    category = ActionCategory.EMPLOYEE_LIFECYCLE

    def generate(self) -> list[ActionItem]:
        from apps.workflows.models import WorkflowTask

        qs = WorkflowTask.objects.filter(
            company_id=self.company_id,
            status='open',
        ).order_by('-created_at')[:50]

        if self.employee_ids is not None:
            qs = qs.filter(assigned_to__in=self.employee_ids)

        now = timezone.now()
        items = []
        for task in qs:
            age = (now - task.created_at).total_seconds() / 3600
            priority = _PRIORITY_MAP.get(task.priority, ActionPriority.MEDIUM)
            items.append(ActionItem(
                id=self.make_id('workflows', str(task.id), 'WORKFLOW_TASK'),
                action_type='WORKFLOW_TASK',
                category=ActionCategory.EMPLOYEE_LIFECYCLE,
                priority=priority,
                title=task.title,
                description=task.description or f'Workflow task ({task.priority} priority)',
                source_module='workflows',
                source_record_id=str(task.id),
                action_url=f'/workflows/tasks/{task.id}/',
                age_hours=age,
                due_date=task.due_date,
            ))
        return items
