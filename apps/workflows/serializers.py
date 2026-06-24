from rest_framework import serializers

from .models import WorkflowDefinition, WorkflowExecution, WorkflowExecutionLog, WorkflowTask


class WorkflowDefinitionSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkflowDefinition
        fields = [
            'id', 'company_id', 'tenant_id', 'name', 'description',
            'trigger_type', 'condition_logic', 'conditions', 'actions',
            'is_active', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class WorkflowExecutionLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkflowExecutionLog
        fields = ['id', 'step', 'action_type', 'status', 'message', 'executed_at']


class WorkflowExecutionSerializer(serializers.ModelSerializer):
    logs = WorkflowExecutionLogSerializer(many=True, read_only=True)
    workflow_name = serializers.CharField(source='workflow.name', read_only=True)

    class Meta:
        model = WorkflowExecution
        fields = [
            'id', 'workflow', 'workflow_name', 'trigger_type', 'source_object_id',
            'status', 'context', 'error_message', 'started_at', 'completed_at',
            'attempt_count', 'company_id', 'created_at', 'updated_at', 'logs',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'logs', 'workflow_name']


class WorkflowTaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkflowTask
        fields = [
            'id', 'company_id', 'tenant_id', 'execution', 'title', 'description',
            'assigned_to', 'due_date', 'status', 'priority', 'completed_at',
            'source_module', 'source_record_id', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'completed_at']
