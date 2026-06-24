import django.db.models.deletion
import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='WorkflowDefinition',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('company_id', models.UUIDField(db_index=True)),
                ('tenant_id', models.UUIDField(blank=True, db_index=True, null=True)),
                ('name', models.CharField(max_length=200)),
                ('description', models.TextField(blank=True, default='')),
                ('trigger_type', models.CharField(
                    choices=[
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
                    ],
                    max_length=100,
                )),
                ('condition_logic', models.CharField(
                    choices=[
                        ('AND', 'All conditions must match'),
                        ('OR', 'Any condition must match'),
                    ],
                    default='AND',
                    max_length=3,
                )),
                ('conditions', models.JSONField(default=list)),
                ('actions', models.JSONField(default=list)),
                ('is_active', models.BooleanField(default=True)),
            ],
            options={'db_table': 'workflow_definitions'},
        ),
        migrations.AddIndex(
            model_name='workflowdefinition',
            index=models.Index(
                fields=['company_id', 'trigger_type', 'is_active'],
                name='wf_def_company_trigger_idx',
            ),
        ),
        migrations.CreateModel(
            name='WorkflowExecution',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('company_id', models.UUIDField(db_index=True)),
                ('tenant_id', models.UUIDField(blank=True, db_index=True, null=True)),
                ('workflow', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='executions',
                    to='workflows.workflowdefinition',
                )),
                ('trigger_type', models.CharField(max_length=100)),
                ('source_object_id', models.CharField(max_length=200)),
                ('status', models.CharField(
                    choices=[
                        ('pending', 'Pending'),
                        ('running', 'Running'),
                        ('completed', 'Completed'),
                        ('failed', 'Failed'),
                        ('skipped', 'Skipped'),
                    ],
                    default='pending',
                    max_length=20,
                )),
                ('context', models.JSONField(default=dict)),
                ('error_message', models.TextField(blank=True, default='')),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('attempt_count', models.PositiveIntegerField(default=0)),
            ],
            options={'db_table': 'workflow_executions'},
        ),
        migrations.CreateModel(
            name='WorkflowExecutionLog',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('execution', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='logs',
                    to='workflows.workflowexecution',
                )),
                ('step', models.PositiveIntegerField()),
                ('action_type', models.CharField(max_length=100)),
                ('status', models.CharField(max_length=20)),
                ('message', models.TextField(blank=True, default='')),
                ('executed_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'db_table': 'workflow_execution_logs',
                'ordering': ['step'],
            },
        ),
        migrations.CreateModel(
            name='WorkflowTask',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('company_id', models.UUIDField(db_index=True)),
                ('tenant_id', models.UUIDField(blank=True, db_index=True, null=True)),
                ('execution', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='tasks',
                    to='workflows.workflowexecution',
                )),
                ('title', models.CharField(max_length=300)),
                ('description', models.TextField(blank=True, default='')),
                ('assigned_to', models.UUIDField(blank=True, db_index=True, null=True)),
                ('due_date', models.DateTimeField(blank=True, null=True)),
                ('status', models.CharField(
                    choices=[
                        ('open', 'Open'),
                        ('in_progress', 'In Progress'),
                        ('completed', 'Completed'),
                        ('cancelled', 'Cancelled'),
                    ],
                    default='open',
                    max_length=20,
                )),
                ('priority', models.CharField(
                    choices=[
                        ('low', 'Low'),
                        ('normal', 'Normal'),
                        ('high', 'High'),
                        ('urgent', 'Urgent'),
                    ],
                    default='normal',
                    max_length=20,
                )),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('source_module', models.CharField(blank=True, default='', max_length=100)),
                ('source_record_id', models.CharField(blank=True, default='', max_length=200)),
            ],
            options={'db_table': 'workflow_tasks'},
        ),
        migrations.AddIndex(
            model_name='workflowtask',
            index=models.Index(
                fields=['company_id', 'status'],
                name='wf_task_company_status_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='workflowtask',
            index=models.Index(
                fields=['assigned_to', 'status'],
                name='wf_task_assigned_status_idx',
            ),
        ),
    ]
