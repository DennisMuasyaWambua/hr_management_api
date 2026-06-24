import uuid

from django.db import models

from apps.hr.models import TenantStamped


class PerformanceGoal(TenantStamped):
    STATUS = [('draft', 'Draft'), ('active', 'Active'),
              ('completed', 'Completed'), ('cancelled', 'Cancelled')]
    CATEGORY = [('okr', 'OKR'), ('kpi', 'KPI'),
                ('development', 'Development'), ('other', 'Other')]

    employee_id = models.UUIDField(db_index=True)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default='')
    category = models.CharField(max_length=20, choices=CATEGORY, default='okr')
    status = models.CharField(max_length=20, choices=STATUS, default='draft')
    target_value = models.FloatField(null=True, blank=True)
    current_value = models.FloatField(default=0)
    due_date = models.DateField(null=True, blank=True)
    period_year = models.IntegerField()
    period_quarter = models.IntegerField(null=True, blank=True)
    owner_id = models.UUIDField(null=True, blank=True)
    weight = models.FloatField(default=1.0)
    is_deleted = models.BooleanField(default=False)

    class Meta:
        db_table = 'perf_goals'
        ordering = ['-period_year', '-created_at']
        indexes = [
            models.Index(fields=['company_id', 'employee_id'],
                         name='pg_co_emp_idx'),
        ]


class GoalUpdate(TenantStamped):
    goal = models.ForeignKey(PerformanceGoal, on_delete=models.CASCADE,
                              related_name='updates')
    progress_pct = models.FloatField()
    current_value = models.FloatField(null=True, blank=True)
    note = models.TextField(blank=True, default='')
    author_id = models.UUIDField(null=True, blank=True)

    class Meta:
        db_table = 'perf_goal_updates'
        ordering = ['-created_at']


class Competency(TenantStamped):
    CATEGORY = [('technical', 'Technical'), ('leadership', 'Leadership'),
                ('behavioural', 'Behavioural'), ('functional', 'Functional')]

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default='')
    category = models.CharField(max_length=20, choices=CATEGORY, default='technical')
    is_active = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False)

    class Meta:
        db_table = 'perf_competencies'
        ordering = ['name']


class CompetencyRating(TenantStamped):
    employee_id = models.UUIDField(db_index=True)
    competency = models.ForeignKey(Competency, on_delete=models.CASCADE,
                                   related_name='ratings')
    rating = models.PositiveSmallIntegerField()
    review_cycle = models.CharField(max_length=20)
    rated_by = models.UUIDField(null=True, blank=True)
    notes = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'perf_competency_ratings'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['company_id', 'employee_id'],
                         name='cr_co_emp_idx'),
        ]


class DevelopmentPlan(TenantStamped):
    STATUS = [('draft', 'Draft'), ('active', 'Active'), ('completed', 'Completed')]

    employee_id = models.UUIDField(db_index=True)
    title = models.CharField(max_length=200)
    period_year = models.IntegerField()
    status = models.CharField(max_length=20, choices=STATUS, default='draft')
    summary = models.TextField(blank=True, default='')
    owner_id = models.UUIDField(null=True, blank=True)
    is_deleted = models.BooleanField(default=False)

    class Meta:
        db_table = 'perf_development_plans'
        ordering = ['-period_year', '-created_at']


class DevelopmentPlanItem(TenantStamped):
    TYPE = [('goal', 'Goal'), ('competency', 'Competency Gap'),
            ('course', 'LMS Course'), ('action', 'Action Item')]

    plan = models.ForeignKey(DevelopmentPlan, on_delete=models.CASCADE,
                             related_name='items')
    item_type = models.CharField(max_length=20, choices=TYPE)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default='')
    due_date = models.DateField(null=True, blank=True)
    is_done = models.BooleanField(default=False)
    goal_id = models.UUIDField(null=True, blank=True)
    competency_id = models.UUIDField(null=True, blank=True)
    course_id = models.UUIDField(null=True, blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'perf_dev_plan_items'
        ordering = ['order']


class FeedbackRequest(TenantStamped):
    STATUS = [('open', 'Open'), ('closed', 'Closed'), ('cancelled', 'Cancelled')]

    subject_id = models.UUIDField(db_index=True)
    requester_id = models.UUIDField()
    review_cycle = models.CharField(max_length=20)
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS, default='open')
    is_anonymous = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False)

    class Meta:
        db_table = 'perf_feedback_requests'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['company_id', 'subject_id'],
                         name='fr_co_sub_idx'),
        ]


class FeedbackResponse(TenantStamped):
    request = models.ForeignKey(FeedbackRequest, on_delete=models.CASCADE,
                                related_name='responses')
    reviewer_id = models.UUIDField()
    overall_rating = models.PositiveSmallIntegerField()
    strengths = models.TextField(blank=True, default='')
    improvements = models.TextField(blank=True, default='')
    answers = models.JSONField(default=dict)
    submitted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'perf_feedback_responses'
        ordering = ['-created_at']
