import uuid
from unittest.mock import MagicMock, patch

from django.test import TestCase

from apps.workflows.engine import WorkflowEngine
from apps.workflows.models import (
    WorkflowDefinition,
    WorkflowExecution,
    WorkflowExecutionLog,
    WorkflowTask,
)

COMPANY = uuid.UUID('00000000-0000-0000-0000-000000000020')
SOURCE_ID = str(uuid.uuid4())


def _make_workflow(**kwargs):
    defaults = dict(
        company_id=COMPANY,
        name='Test WF',
        trigger_type='candidate_applied',
        conditions=[],
        actions=[],
        is_active=True,
    )
    defaults.update(kwargs)
    return WorkflowDefinition.objects.create(**defaults)


class TestWorkflowEngineFire(TestCase):

    def test_fire_no_matching_workflows_returns_empty(self):
        result = WorkflowEngine.fire('candidate_applied', {'id': SOURCE_ID}, COMPANY)
        self.assertEqual(result, [])

    def test_fire_inactive_workflow_skipped(self):
        _make_workflow(is_active=False)
        result = WorkflowEngine.fire('candidate_applied', {'id': SOURCE_ID}, COMPANY)
        self.assertEqual(result, [])

    def test_fire_wrong_trigger_type_skipped(self):
        _make_workflow(trigger_type='leave_submitted')
        result = WorkflowEngine.fire('candidate_applied', {'id': SOURCE_ID}, COMPANY)
        self.assertEqual(result, [])

    def test_fire_wrong_company_skipped(self):
        _make_workflow()
        other_company = uuid.UUID('00000000-0000-0000-0000-000000000099')
        result = WorkflowEngine.fire('candidate_applied', {'id': SOURCE_ID}, other_company)
        self.assertEqual(result, [])

    def test_fire_creates_execution(self):
        _make_workflow()
        result = WorkflowEngine.fire('candidate_applied', {'id': SOURCE_ID}, COMPANY)
        self.assertEqual(len(result), 1)
        ex = result[0]
        self.assertEqual(ex.trigger_type, 'candidate_applied')
        self.assertEqual(ex.source_object_id, SOURCE_ID)
        self.assertEqual(str(ex.company_id), str(COMPANY))

    def test_fire_invalid_company_id_returns_empty(self):
        result = WorkflowEngine.fire('candidate_applied', {'id': SOURCE_ID}, 'not-a-uuid')
        self.assertEqual(result, [])

    def test_fire_no_conditions_completes(self):
        _make_workflow(conditions=[])
        result = WorkflowEngine.fire('candidate_applied', {'id': SOURCE_ID}, COMPANY)
        self.assertEqual(result[0].status, 'completed')

    def test_fire_conditions_not_met_status_skipped(self):
        conditions = [{'field': 'score', 'operator': 'gte', 'value': '90'}]
        _make_workflow(conditions=conditions)
        result = WorkflowEngine.fire('candidate_applied', {'id': SOURCE_ID, 'score': '50'}, COMPANY)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].status, 'skipped')

    def test_fire_conditions_met_status_completed(self):
        conditions = [{'field': 'score', 'operator': 'gte', 'value': '90'}]
        _make_workflow(conditions=conditions)
        result = WorkflowEngine.fire('candidate_applied', {'id': SOURCE_ID, 'score': '95'}, COMPANY)
        self.assertEqual(result[0].status, 'completed')

    def test_fire_logs_condition_skip(self):
        conditions = [{'field': 'score', 'operator': 'gte', 'value': '90'}]
        _make_workflow(conditions=conditions)
        result = WorkflowEngine.fire('candidate_applied', {'id': SOURCE_ID, 'score': '50'}, COMPANY)
        logs = list(result[0].logs.all())
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0].status, 'skipped')

    def test_fire_context_stored_on_execution(self):
        _make_workflow()
        ctx = {'id': SOURCE_ID, 'candidate_name': 'Alice'}
        result = WorkflowEngine.fire('candidate_applied', ctx, COMPANY)
        self.assertEqual(result[0].context['candidate_name'], 'Alice')

    def test_fire_attempt_count_increments(self):
        wf = _make_workflow()
        ctx = {'id': SOURCE_ID}
        WorkflowEngine.fire('candidate_applied', ctx, COMPANY)
        first = WorkflowExecution.objects.filter(workflow=wf).first()
        self.assertEqual(first.attempt_count, 1)

    def test_idempotency_completed_execution_not_duplicated(self):
        wf = _make_workflow()
        ctx = {'id': SOURCE_ID}
        result1 = WorkflowEngine.fire('candidate_applied', ctx, COMPANY)
        self.assertEqual(result1[0].status, 'completed')
        # Second fire for same source_object_id should be skipped (already completed)
        result2 = WorkflowEngine.fire('candidate_applied', ctx, COMPANY)
        self.assertEqual(result2, [])
        # Only one execution record exists for this source object
        count = WorkflowExecution.objects.filter(
            workflow=wf, source_object_id=SOURCE_ID, status='completed'
        ).count()
        self.assertEqual(count, 1)


class TestWorkflowEngineActions(TestCase):

    def test_create_task_action_executed(self):
        actions = [
            {'type': 'create_task', 'params': {'title': 'Review {{candidate_name}}', 'priority': 'high'}},
        ]
        wf = _make_workflow(actions=actions)
        ctx = {'id': SOURCE_ID, 'candidate_name': 'Bob', 'company_id': str(COMPANY)}
        result = WorkflowEngine.fire('candidate_applied', ctx, COMPANY)
        self.assertEqual(result[0].status, 'completed')
        task = WorkflowTask.objects.filter(execution=result[0]).first()
        self.assertIsNotNone(task)
        self.assertEqual(task.title, 'Review Bob')
        self.assertEqual(task.priority, 'high')

    def test_action_log_created_per_step(self):
        actions = [
            {'type': 'create_task', 'params': {'title': 'Task 1'}},
            {'type': 'create_task', 'params': {'title': 'Task 2'}},
        ]
        _make_workflow(actions=actions)
        ctx = {'id': SOURCE_ID}
        result = WorkflowEngine.fire('candidate_applied', ctx, COMPANY)
        logs = list(result[0].logs.all())
        self.assertEqual(len(logs), 2)
        self.assertEqual(logs[0].step, 0)
        self.assertEqual(logs[1].step, 1)

    def test_unknown_action_type_logs_skipped(self):
        actions = [{'type': 'nonexistent_action', 'params': {}}]
        _make_workflow(actions=actions)
        result = WorkflowEngine.fire('candidate_applied', {'id': SOURCE_ID}, COMPANY)
        log = result[0].logs.first()
        self.assertEqual(log.status, 'skipped')
        self.assertIn('No executor', log.message)

    def test_failed_action_marks_execution_failed(self):
        actions = [{'type': 'send_email', 'params': {'recipient': 'test@example.com', 'subject': 'Hi', 'body': 'Test'}}]
        _make_workflow(actions=actions)
        from apps.workflows import executors
        with patch.object(executors.SendEmailExecutor, 'execute', side_effect=Exception('SMTP down')):
            result = WorkflowEngine.fire('candidate_applied', {'id': SOURCE_ID}, COMPANY)
        self.assertEqual(result[0].status, 'failed')

    def test_multiple_workflows_for_same_trigger(self):
        _make_workflow(name='WF1')
        _make_workflow(name='WF2')
        result = WorkflowEngine.fire('candidate_applied', {'id': SOURCE_ID}, COMPANY)
        self.assertEqual(len(result), 2)


class TestWorkflowEngineOrLogic(TestCase):

    def test_or_logic_one_condition_matches(self):
        conditions = [
            {'field': 'stage', 'operator': 'eq', 'value': 'screened'},
            {'field': 'stage', 'operator': 'eq', 'value': 'interview_l1'},
        ]
        wf = _make_workflow(conditions=conditions, condition_logic='OR')
        ctx = {'id': SOURCE_ID, 'stage': 'screened'}
        result = WorkflowEngine.fire('candidate_applied', ctx, COMPANY)
        self.assertEqual(result[0].status, 'completed')

    def test_or_logic_no_condition_matches(self):
        conditions = [
            {'field': 'stage', 'operator': 'eq', 'value': 'hired'},
            {'field': 'stage', 'operator': 'eq', 'value': 'rejected'},
        ]
        wf = _make_workflow(conditions=conditions, condition_logic='OR')
        ctx = {'id': SOURCE_ID, 'stage': 'screened'}
        result = WorkflowEngine.fire('candidate_applied', ctx, COMPANY)
        self.assertEqual(result[0].status, 'skipped')
