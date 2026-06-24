import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('hr', '0006_exitclearance'),
    ]

    operations = [
        migrations.CreateModel(
            name='PerformanceGoal',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('tenant_id', models.UUIDField(db_index=True, null=True, blank=True)),
                ('company_id', models.UUIDField(db_index=True, null=True, blank=True)),
                ('employee_id', models.UUIDField(db_index=True)),
                ('title', models.CharField(max_length=200)),
                ('description', models.TextField(blank=True, default='')),
                ('category', models.CharField(
                    choices=[('okr', 'OKR'), ('kpi', 'KPI'),
                             ('development', 'Development'), ('other', 'Other')],
                    default='okr', max_length=20)),
                ('status', models.CharField(
                    choices=[('draft', 'Draft'), ('active', 'Active'),
                             ('completed', 'Completed'), ('cancelled', 'Cancelled')],
                    default='draft', max_length=20)),
                ('target_value', models.FloatField(blank=True, null=True)),
                ('current_value', models.FloatField(default=0)),
                ('due_date', models.DateField(blank=True, null=True)),
                ('period_year', models.IntegerField()),
                ('period_quarter', models.IntegerField(blank=True, null=True)),
                ('owner_id', models.UUIDField(blank=True, null=True)),
                ('weight', models.FloatField(default=1.0)),
                ('is_deleted', models.BooleanField(default=False)),
            ],
            options={'db_table': 'perf_goals', 'ordering': ['-period_year', '-created_at']},
        ),
        migrations.AddIndex(
            model_name='performancegoal',
            index=models.Index(fields=['company_id', 'employee_id'], name='pg_co_emp_idx'),
        ),
        migrations.CreateModel(
            name='GoalUpdate',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('tenant_id', models.UUIDField(db_index=True, null=True, blank=True)),
                ('company_id', models.UUIDField(db_index=True, null=True, blank=True)),
                ('goal', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='updates', to='performance.performancegoal')),
                ('progress_pct', models.FloatField()),
                ('current_value', models.FloatField(blank=True, null=True)),
                ('note', models.TextField(blank=True, default='')),
                ('author_id', models.UUIDField(blank=True, null=True)),
            ],
            options={'db_table': 'perf_goal_updates', 'ordering': ['-created_at']},
        ),
        migrations.CreateModel(
            name='Competency',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('tenant_id', models.UUIDField(db_index=True, null=True, blank=True)),
                ('company_id', models.UUIDField(db_index=True, null=True, blank=True)),
                ('name', models.CharField(max_length=200)),
                ('description', models.TextField(blank=True, default='')),
                ('category', models.CharField(
                    choices=[('technical', 'Technical'), ('leadership', 'Leadership'),
                             ('behavioural', 'Behavioural'), ('functional', 'Functional')],
                    default='technical', max_length=20)),
                ('is_active', models.BooleanField(default=True)),
                ('is_deleted', models.BooleanField(default=False)),
            ],
            options={'db_table': 'perf_competencies', 'ordering': ['name']},
        ),
        migrations.CreateModel(
            name='CompetencyRating',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('tenant_id', models.UUIDField(db_index=True, null=True, blank=True)),
                ('company_id', models.UUIDField(db_index=True, null=True, blank=True)),
                ('employee_id', models.UUIDField(db_index=True)),
                ('competency', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='ratings', to='performance.competency')),
                ('rating', models.PositiveSmallIntegerField()),
                ('review_cycle', models.CharField(max_length=20)),
                ('rated_by', models.UUIDField(blank=True, null=True)),
                ('notes', models.TextField(blank=True, default='')),
            ],
            options={'db_table': 'perf_competency_ratings', 'ordering': ['-created_at']},
        ),
        migrations.AddIndex(
            model_name='competencyrating',
            index=models.Index(fields=['company_id', 'employee_id'], name='cr_co_emp_idx'),
        ),
        migrations.CreateModel(
            name='DevelopmentPlan',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('tenant_id', models.UUIDField(db_index=True, null=True, blank=True)),
                ('company_id', models.UUIDField(db_index=True, null=True, blank=True)),
                ('employee_id', models.UUIDField(db_index=True)),
                ('title', models.CharField(max_length=200)),
                ('period_year', models.IntegerField()),
                ('status', models.CharField(
                    choices=[('draft', 'Draft'), ('active', 'Active'),
                             ('completed', 'Completed')],
                    default='draft', max_length=20)),
                ('summary', models.TextField(blank=True, default='')),
                ('owner_id', models.UUIDField(blank=True, null=True)),
                ('is_deleted', models.BooleanField(default=False)),
            ],
            options={'db_table': 'perf_development_plans',
                     'ordering': ['-period_year', '-created_at']},
        ),
        migrations.CreateModel(
            name='DevelopmentPlanItem',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('tenant_id', models.UUIDField(db_index=True, null=True, blank=True)),
                ('company_id', models.UUIDField(db_index=True, null=True, blank=True)),
                ('plan', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='items', to='performance.developmentplan')),
                ('item_type', models.CharField(
                    choices=[('goal', 'Goal'), ('competency', 'Competency Gap'),
                             ('course', 'LMS Course'), ('action', 'Action Item')],
                    max_length=20)),
                ('title', models.CharField(max_length=200)),
                ('description', models.TextField(blank=True, default='')),
                ('due_date', models.DateField(blank=True, null=True)),
                ('is_done', models.BooleanField(default=False)),
                ('goal_id', models.UUIDField(blank=True, null=True)),
                ('competency_id', models.UUIDField(blank=True, null=True)),
                ('course_id', models.UUIDField(blank=True, null=True)),
                ('order', models.PositiveIntegerField(default=0)),
            ],
            options={'db_table': 'perf_dev_plan_items', 'ordering': ['order']},
        ),
        migrations.CreateModel(
            name='FeedbackRequest',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('tenant_id', models.UUIDField(db_index=True, null=True, blank=True)),
                ('company_id', models.UUIDField(db_index=True, null=True, blank=True)),
                ('subject_id', models.UUIDField(db_index=True)),
                ('requester_id', models.UUIDField()),
                ('review_cycle', models.CharField(max_length=20)),
                ('due_date', models.DateField(blank=True, null=True)),
                ('status', models.CharField(
                    choices=[('open', 'Open'), ('closed', 'Closed'),
                             ('cancelled', 'Cancelled')],
                    default='open', max_length=20)),
                ('is_anonymous', models.BooleanField(default=True)),
                ('is_deleted', models.BooleanField(default=False)),
            ],
            options={'db_table': 'perf_feedback_requests', 'ordering': ['-created_at']},
        ),
        migrations.AddIndex(
            model_name='feedbackrequest',
            index=models.Index(fields=['company_id', 'subject_id'], name='fr_co_sub_idx'),
        ),
        migrations.CreateModel(
            name='FeedbackResponse',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('tenant_id', models.UUIDField(db_index=True, null=True, blank=True)),
                ('company_id', models.UUIDField(db_index=True, null=True, blank=True)),
                ('request', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='responses', to='performance.feedbackrequest')),
                ('reviewer_id', models.UUIDField()),
                ('overall_rating', models.PositiveSmallIntegerField()),
                ('strengths', models.TextField(blank=True, default='')),
                ('improvements', models.TextField(blank=True, default='')),
                ('answers', models.JSONField(default=dict)),
                ('submitted_at', models.DateTimeField(blank=True, null=True)),
            ],
            options={'db_table': 'perf_feedback_responses', 'ordering': ['-created_at']},
        ),
        migrations.AddConstraint(
            model_name='feedbackresponse',
            constraint=models.UniqueConstraint(
                fields=['request', 'reviewer_id'], name='perf_fr_reviewer_uniq'),
        ),
    ]
