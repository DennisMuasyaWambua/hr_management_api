import uuid

from django.db import models


TRIGGER_TYPES = [
    ('candidate_applied', 'Candidate Applied'),
    ('candidate_stage_changed', 'Candidate Stage Changed'),
    ('interview_completed', 'Interview Completed'),
    ('employee_created', 'Employee Created'),
    ('leave_submitted', 'Leave Submitted'),
    ('leave_approved', 'Leave Approved'),
    ('leave_rejected', 'Leave Rejected'),
    ('contract_expiring', 'Contract Expiring'),
    ('performance_review_due', 'Performance Review Due'),
    ('exit_process_started', 'Exit Process Started'),
]

EXECUTION_STATUS = [
    ('pending', 'Pending'),
    ('running', 'Running'),
    ('completed', 'Completed'),
    ('failed', 'Failed'),
    ('skipped', 'Skipped'),
]

CONDITION_LOGIC = [
    ('AND', 'All conditions must match'),
    ('OR', 'Any condition must match'),
]

TASK_STATUS = [
    ('open', 'Open'),
    ('in_progress', 'In Progress'),
    ('completed', 'Completed'),
    ('cancelled', 'Cancelled'),
]

TASK_PRIORITY = [
    ('low', 'Low'),
    ('normal', 'Normal'),
    ('high', 'High'),
    ('urgent', 'Urgent'),
]


class WorkflowDefinition(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    company_id = models.UUIDField(db_index=True)
    tenant_id = models.UUIDField(null=True, blank=True, db_index=True)

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default='')
    trigger_type = models.CharField(max_length=100, choices=TRIGGER_TYPES)
    condition_logic = models.CharField(max_length=3, choices=CONDITION_LOGIC, default='AND')
    conditions = models.JSONField(default=list)
    actions = models.JSONField(default=list)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'workflow_definitions'
        indexes = [
            models.Index(
                fields=['company_id', 'trigger_type', 'is_active'],
                name='wf_def_company_trigger_idx',
            ),
        ]

    def __str__(self):
        return f'{self.name} [{self.trigger_type}]'


class WorkflowExecution(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    company_id = models.UUIDField(db_index=True)
    tenant_id = models.UUIDField(null=True, blank=True, db_index=True)

    workflow = models.ForeignKey(
        WorkflowDefinition, on_delete=models.CASCADE, related_name='executions',
    )
    trigger_type = models.CharField(max_length=100)
    source_object_id = models.CharField(max_length=200)
    status = models.CharField(max_length=20, choices=EXECUTION_STATUS, default='pending')
    context = models.JSONField(default=dict)
    error_message = models.TextField(blank=True, default='')
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    attempt_count = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'workflow_executions'

    def __str__(self):
        return f'{self.workflow.name} / {self.source_object_id} [{self.status}]'


class WorkflowExecutionLog(models.Model):
    id = models.BigAutoField(primary_key=True)
    execution = models.ForeignKey(
        WorkflowExecution, on_delete=models.CASCADE, related_name='logs',
    )
    step = models.PositiveIntegerField()
    action_type = models.CharField(max_length=100)
    status = models.CharField(max_length=20)
    message = models.TextField(blank=True, default='')
    executed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'workflow_execution_logs'
        ordering = ['step']


class WorkflowTask(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    company_id = models.UUIDField(db_index=True)
    tenant_id = models.UUIDField(null=True, blank=True, db_index=True)

    execution = models.ForeignKey(
        WorkflowExecution, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='tasks',
    )
    title = models.CharField(max_length=300)
    description = models.TextField(blank=True, default='')
    assigned_to = models.UUIDField(null=True, blank=True, db_index=True)
    due_date = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=TASK_STATUS, default='open')
    priority = models.CharField(max_length=20, choices=TASK_PRIORITY, default='normal')
    completed_at = models.DateTimeField(null=True, blank=True)
    source_module = models.CharField(max_length=100, blank=True, default='')
    source_record_id = models.CharField(max_length=200, blank=True, default='')

    class Meta:
        db_table = 'workflow_tasks'
        indexes = [
            models.Index(fields=['company_id', 'status'], name='wf_task_company_status_idx'),
            models.Index(fields=['assigned_to', 'status'], name='wf_task_assigned_status_idx'),
        ]

    def __str__(self):
        return self.title
