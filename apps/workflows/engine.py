import logging
from uuid import UUID

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


class WorkflowEngine:

    @classmethod
    def fire(cls, trigger_type: str, context: dict, company_id) -> list:
        """Find and execute all active matching workflows for this trigger/company."""
        try:
            company_uuid = UUID(str(company_id))
        except (ValueError, AttributeError):
            logger.error('WorkflowEngine.fire: invalid company_id %r', company_id)
            return []

        from .models import WorkflowDefinition
        workflows = list(
            WorkflowDefinition.objects.filter(
                trigger_type=trigger_type,
                is_active=True,
                company_id=company_uuid,
            )
        )

        executions = []
        for workflow in workflows:
            try:
                execution = cls._execute(workflow, context, company_uuid)
                if execution is not None:
                    executions.append(execution)
            except Exception:
                logger.exception(
                    'WorkflowEngine: unhandled error in workflow %s', workflow.id
                )
        return executions

    @classmethod
    def _execute(cls, workflow, context: dict, company_id: UUID):
        from .conditions import ConditionEvaluator
        from .executors import ExecutorRegistry
        from .models import WorkflowExecution, WorkflowExecutionLog

        source_object_id = str(
            context.get('id') or context.get('source_object_id') or ''
        )

        # Idempotency: don't re-run a completed execution for this object
        if WorkflowExecution.objects.filter(
            workflow=workflow,
            source_object_id=source_object_id,
            trigger_type=workflow.trigger_type,
            status='completed',
        ).exists():
            return None

        prior = WorkflowExecution.objects.filter(
            workflow=workflow,
            source_object_id=source_object_id,
            trigger_type=workflow.trigger_type,
        ).first()

        execution = WorkflowExecution.objects.create(
            workflow=workflow,
            trigger_type=workflow.trigger_type,
            source_object_id=source_object_id,
            status='running',
            context=context,
            company_id=company_id,
            tenant_id=workflow.tenant_id,
            started_at=timezone.now(),
            attempt_count=(prior.attempt_count + 1) if prior else 1,
        )

        conditions_met = ConditionEvaluator.evaluate(
            workflow.conditions, context, workflow.condition_logic
        )
        if not conditions_met:
            execution.status = 'skipped'
            execution.completed_at = timezone.now()
            execution.save(update_fields=['status', 'completed_at', 'updated_at'])
            WorkflowExecutionLog.objects.create(
                execution=execution, step=0,
                action_type='condition_check', status='skipped',
                message='Conditions not met — workflow skipped',
            )
            return execution

        all_succeeded = True
        with transaction.atomic():
            for i, action_def in enumerate(workflow.actions):
                action_type = action_def.get('type', 'unknown')
                params = action_def.get('params', {})
                try:
                    executor = ExecutorRegistry.get(action_type)
                    if executor is None:
                        message = f'No executor for action type: {action_type}'
                        log_status = 'skipped'
                    else:
                        message = executor.execute(params, context, execution)
                        log_status = 'success'
                except Exception as exc:
                    message = str(exc)
                    log_status = 'failed'
                    all_succeeded = False
                    logger.exception(
                        'Action %s (step %d) failed in workflow %s',
                        action_type, i, workflow.id,
                    )
                WorkflowExecutionLog.objects.create(
                    execution=execution, step=i,
                    action_type=action_type, status=log_status, message=message,
                )

        execution.status = 'completed' if all_succeeded else 'failed'
        execution.completed_at = timezone.now()
        execution.save(update_fields=['status', 'completed_at', 'updated_at'])

        try:
            from apps.core.models import ServiceAuditLog
            ServiceAuditLog.log(
                'workflow.executed',
                company_id=str(company_id),
                metadata={
                    'workflow_id': str(workflow.id),
                    'workflow_name': workflow.name,
                    'trigger': workflow.trigger_type,
                    'status': execution.status,
                    'source_object_id': source_object_id,
                },
            )
        except Exception:
            logger.exception('Failed to write workflow audit log')

        return execution
