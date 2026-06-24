import uuid

from django.test import TestCase

from apps.workflows.models import (
    WorkflowDefinition,
    WorkflowExecution,
    WorkflowExecutionLog,
    WorkflowTask,
)

COMPANY = uuid.UUID('00000000-0000-0000-0000-000000000010')


def _make_definition(**kwargs):
    defaults = dict(
        company_id=COMPANY,
        name='Test Workflow',
        trigger_type='candidate_applied',
        conditions=[],
        actions=[],
    )
    defaults.update(kwargs)
    return WorkflowDefinition.objects.create(**defaults)


class TestWorkflowDefinition(TestCase):

    def test_create_minimal(self):
        wf = _make_definition()
        self.assertIsNotNone(wf.id)
        self.assertEqual(wf.trigger_type, 'candidate_applied')
        self.assertTrue(wf.is_active)
        self.assertEqual(wf.condition_logic, 'AND')

    def test_str(self):
        wf = _make_definition(name='My Workflow')
        self.assertIn('My Workflow', str(wf))
        self.assertIn('candidate_applied', str(wf))

    def test_conditions_default_empty_list(self):
        wf = _make_definition()
        self.assertEqual(wf.conditions, [])

    def test_actions_default_empty_list(self):
        wf = _make_definition()
        self.assertEqual(wf.actions, [])


class TestWorkflowExecution(TestCase):

    def setUp(self):
        self.wf = _make_definition()

    def test_create(self):
        ex = WorkflowExecution.objects.create(
            workflow=self.wf,
            trigger_type='candidate_applied',
            source_object_id='abc-123',
            status='completed',
            company_id=COMPANY,
        )
        self.assertEqual(ex.status, 'completed')
        self.assertEqual(ex.attempt_count, 0)

    def test_str(self):
        ex = WorkflowExecution.objects.create(
            workflow=self.wf,
            trigger_type='candidate_applied',
            source_object_id='abc-123',
            status='running',
            company_id=COMPANY,
        )
        self.assertIn('running', str(ex))

    def test_cascade_delete(self):
        ex = WorkflowExecution.objects.create(
            workflow=self.wf,
            trigger_type='candidate_applied',
            source_object_id='abc-123',
            company_id=COMPANY,
        )
        ex_id = ex.id
        self.wf.delete()
        self.assertFalse(WorkflowExecution.objects.filter(id=ex_id).exists())


class TestWorkflowExecutionLog(TestCase):

    def setUp(self):
        self.wf = _make_definition()
        self.ex = WorkflowExecution.objects.create(
            workflow=self.wf,
            trigger_type='candidate_applied',
            source_object_id='abc',
            company_id=COMPANY,
        )

    def test_create(self):
        log = WorkflowExecutionLog.objects.create(
            execution=self.ex,
            step=0,
            action_type='send_email',
            status='success',
            message='Email sent',
        )
        self.assertEqual(log.step, 0)
        self.assertEqual(log.status, 'success')

    def test_ordering_by_step(self):
        WorkflowExecutionLog.objects.create(
            execution=self.ex, step=2, action_type='a', status='success',
        )
        WorkflowExecutionLog.objects.create(
            execution=self.ex, step=0, action_type='b', status='success',
        )
        WorkflowExecutionLog.objects.create(
            execution=self.ex, step=1, action_type='c', status='success',
        )
        steps = list(WorkflowExecutionLog.objects.filter(execution=self.ex).values_list('step', flat=True))
        self.assertEqual(steps, [0, 1, 2])


class TestWorkflowTask(TestCase):

    def test_create(self):
        task = WorkflowTask.objects.create(
            company_id=COMPANY,
            title='Review candidate',
            priority='high',
        )
        self.assertEqual(task.status, 'open')
        self.assertEqual(task.priority, 'high')
        self.assertIsNone(task.completed_at)

    def test_str(self):
        task = WorkflowTask.objects.create(
            company_id=COMPANY, title='My Task',
        )
        self.assertEqual(str(task), 'My Task')

    def test_company_isolation_query(self):
        other_company = uuid.UUID('00000000-0000-0000-0000-000000000099')
        WorkflowTask.objects.create(company_id=COMPANY, title='Task A')
        WorkflowTask.objects.create(company_id=other_company, title='Task B')
        tasks = WorkflowTask.objects.filter(company_id=COMPANY)
        self.assertEqual(tasks.count(), 1)
        self.assertEqual(tasks.first().title, 'Task A')
