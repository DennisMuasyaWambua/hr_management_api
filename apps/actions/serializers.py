from rest_framework import serializers


class ActionItemSerializer(serializers.Serializer):
    id = serializers.CharField()
    action_type = serializers.CharField()
    category = serializers.CharField()
    priority = serializers.CharField()
    priority_score = serializers.IntegerField()
    title = serializers.CharField()
    description = serializers.CharField()
    status = serializers.CharField()
    source_module = serializers.CharField()
    source_record_id = serializers.CharField()
    action_url = serializers.CharField()
    due_date = serializers.DateTimeField(allow_null=True)
    age_hours = serializers.FloatField()
    assigned_to = serializers.CharField(allow_null=True)
    first_seen_at = serializers.DateTimeField(allow_null=True)
    dismissed_at = serializers.DateTimeField(allow_null=True)
    escalated_at = serializers.DateTimeField(allow_null=True)


class ActionSummarySerializer(serializers.Serializer):
    total_active = serializers.IntegerField()
    overdue = serializers.IntegerField()
    by_priority = serializers.DictField(child=serializers.IntegerField())
    by_category = serializers.DictField(child=serializers.IntegerField())
    generated_at = serializers.CharField()
