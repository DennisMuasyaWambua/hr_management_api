from rest_framework import serializers

from .models import (Competency, CompetencyRating, DevelopmentPlan,
                     DevelopmentPlanItem, FeedbackRequest, FeedbackResponse,
                     GoalUpdate, PerformanceGoal)


class GoalUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = GoalUpdate
        fields = ['id', 'goal', 'progress_pct', 'current_value', 'note',
                  'author_id', 'created_at']
        read_only_fields = ['id', 'created_at']
        extra_kwargs = {'goal': {'required': False}}


class PerformanceGoalSerializer(serializers.ModelSerializer):
    updates = GoalUpdateSerializer(many=True, read_only=True)
    progress_pct = serializers.SerializerMethodField()

    class Meta:
        model = PerformanceGoal
        fields = ['id', 'employee_id', 'title', 'description', 'category',
                  'status', 'target_value', 'current_value', 'due_date',
                  'period_year', 'period_quarter', 'owner_id', 'weight',
                  'progress_pct', 'updates', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_progress_pct(self, obj):
        if obj.target_value and obj.target_value > 0:
            return round(min(obj.current_value / obj.target_value * 100, 100), 2)
        latest = obj.updates.first()
        return latest.progress_pct if latest else 0.0


class PerformanceGoalListSerializer(serializers.ModelSerializer):
    class Meta:
        model = PerformanceGoal
        fields = ['id', 'employee_id', 'title', 'category', 'status',
                  'current_value', 'target_value', 'due_date', 'period_year',
                  'period_quarter', 'weight', 'created_at']
        read_only_fields = ['id', 'created_at']


class CompetencySerializer(serializers.ModelSerializer):
    class Meta:
        model = Competency
        fields = ['id', 'name', 'description', 'category', 'is_active',
                  'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class CompetencyRatingSerializer(serializers.ModelSerializer):
    competency_name = serializers.CharField(source='competency.name', read_only=True)

    class Meta:
        model = CompetencyRating
        fields = ['id', 'employee_id', 'competency', 'competency_name',
                  'rating', 'review_cycle', 'rated_by', 'notes',
                  'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class DevelopmentPlanItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = DevelopmentPlanItem
        fields = ['id', 'plan', 'item_type', 'title', 'description',
                  'due_date', 'is_done', 'goal_id', 'competency_id',
                  'course_id', 'order', 'created_at']
        read_only_fields = ['id', 'created_at']
        extra_kwargs = {'plan': {'required': False}}


class DevelopmentPlanSerializer(serializers.ModelSerializer):
    items = DevelopmentPlanItemSerializer(many=True, read_only=True)
    item_count = serializers.SerializerMethodField()

    class Meta:
        model = DevelopmentPlan
        fields = ['id', 'employee_id', 'title', 'period_year', 'status',
                  'summary', 'owner_id', 'item_count', 'items',
                  'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_item_count(self, obj):
        return obj.items.count()


class DevelopmentPlanListSerializer(serializers.ModelSerializer):
    class Meta:
        model = DevelopmentPlan
        fields = ['id', 'employee_id', 'title', 'period_year', 'status',
                  'owner_id', 'created_at']
        read_only_fields = ['id', 'created_at']


class FeedbackResponseSerializer(serializers.ModelSerializer):
    class Meta:
        model = FeedbackResponse
        fields = ['id', 'request', 'reviewer_id', 'overall_rating',
                  'strengths', 'improvements', 'answers', 'submitted_at',
                  'created_at']
        read_only_fields = ['id', 'submitted_at', 'created_at']
        extra_kwargs = {'request': {'required': False}}


class FeedbackResponseAnonSerializer(FeedbackResponseSerializer):
    reviewer_id = serializers.SerializerMethodField()

    def get_reviewer_id(self, obj):
        return None


class FeedbackRequestSerializer(serializers.ModelSerializer):
    response_count = serializers.SerializerMethodField()
    avg_rating = serializers.SerializerMethodField()

    class Meta:
        model = FeedbackRequest
        fields = ['id', 'subject_id', 'requester_id', 'review_cycle',
                  'due_date', 'status', 'is_anonymous', 'response_count',
                  'avg_rating', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_response_count(self, obj):
        return obj.responses.count()

    def get_avg_rating(self, obj):
        responses = obj.responses.all()
        if not responses:
            return None
        return round(sum(r.overall_rating for r in responses) / len(responses), 2)
