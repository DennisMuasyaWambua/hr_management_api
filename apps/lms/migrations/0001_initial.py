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
            name='Course',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('tenant_id', models.UUIDField(db_index=True, null=True, blank=True)),
                ('company_id', models.UUIDField(db_index=True, null=True, blank=True)),
                ('title', models.CharField(max_length=200)),
                ('description', models.TextField(blank=True, default='')),
                ('level', models.CharField(
                    choices=[('beginner', 'Beginner'), ('intermediate', 'Intermediate'),
                             ('advanced', 'Advanced')],
                    default='beginner', max_length=20)),
                ('status', models.CharField(
                    choices=[('draft', 'Draft'), ('published', 'Published'),
                             ('archived', 'Archived')],
                    default='draft', max_length=20)),
                ('thumbnail_url', models.TextField(blank=True, null=True)),
                ('author_id', models.UUIDField(blank=True, null=True)),
                ('duration_hours', models.FloatField(default=0)),
                ('is_mandatory', models.BooleanField(default=False)),
                ('department', models.CharField(blank=True, max_length=120, null=True)),
                ('tags', models.JSONField(default=list)),
                ('pass_score', models.FloatField(default=70.0)),
                ('is_deleted', models.BooleanField(default=False)),
            ],
            options={'db_table': 'lms_courses', 'ordering': ['-created_at']},
        ),
        migrations.CreateModel(
            name='CourseModule',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('tenant_id', models.UUIDField(db_index=True, null=True, blank=True)),
                ('company_id', models.UUIDField(db_index=True, null=True, blank=True)),
                ('course', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='modules', to='lms.course')),
                ('title', models.CharField(max_length=200)),
                ('description', models.TextField(blank=True, default='')),
                ('order', models.PositiveIntegerField(default=0)),
                ('is_deleted', models.BooleanField(default=False)),
            ],
            options={'db_table': 'lms_course_modules', 'ordering': ['order']},
        ),
        migrations.AddConstraint(
            model_name='coursemodule',
            constraint=models.UniqueConstraint(
                fields=['course', 'order'], name='lms_mod_course_order_uniq'),
        ),
        migrations.CreateModel(
            name='Lesson',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('tenant_id', models.UUIDField(db_index=True, null=True, blank=True)),
                ('company_id', models.UUIDField(db_index=True, null=True, blank=True)),
                ('module', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='lessons', to='lms.coursemodule')),
                ('title', models.CharField(max_length=200)),
                ('lesson_type', models.CharField(
                    choices=[('text', 'Text'), ('video', 'Video'), ('file', 'File'),
                             ('quiz', 'Quiz'), ('scorm', 'SCORM')],
                    default='text', max_length=20)),
                ('content', models.TextField(blank=True, default='')),
                ('video_url', models.TextField(blank=True, null=True)),
                ('file_url', models.TextField(blank=True, null=True)),
                ('duration_mins', models.PositiveIntegerField(default=0)),
                ('order', models.PositiveIntegerField(default=0)),
                ('is_deleted', models.BooleanField(default=False)),
            ],
            options={'db_table': 'lms_lessons', 'ordering': ['order']},
        ),
        migrations.CreateModel(
            name='Assessment',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('tenant_id', models.UUIDField(db_index=True, null=True, blank=True)),
                ('company_id', models.UUIDField(db_index=True, null=True, blank=True)),
                ('course', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='assessments', to='lms.course')),
                ('title', models.CharField(max_length=200)),
                ('pass_score', models.FloatField(default=70.0)),
                ('time_limit_mins', models.PositiveIntegerField(blank=True, null=True)),
                ('max_attempts', models.PositiveIntegerField(default=3)),
                ('is_deleted', models.BooleanField(default=False)),
            ],
            options={'db_table': 'lms_assessments'},
        ),
        migrations.CreateModel(
            name='AssessmentQuestion',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('tenant_id', models.UUIDField(db_index=True, null=True, blank=True)),
                ('company_id', models.UUIDField(db_index=True, null=True, blank=True)),
                ('assessment', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='questions', to='lms.assessment')),
                ('question', models.TextField()),
                ('question_type', models.CharField(
                    choices=[('mcq', 'Multiple Choice'), ('true_false', 'True/False'),
                             ('short_answer', 'Short Answer')],
                    default='mcq', max_length=20)),
                ('options', models.JSONField(default=list)),
                ('answer', models.JSONField()),
                ('points', models.FloatField(default=1.0)),
                ('order', models.PositiveIntegerField(default=0)),
            ],
            options={'db_table': 'lms_assessment_questions', 'ordering': ['order']},
        ),
        migrations.CreateModel(
            name='LearningPath',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('tenant_id', models.UUIDField(db_index=True, null=True, blank=True)),
                ('company_id', models.UUIDField(db_index=True, null=True, blank=True)),
                ('title', models.CharField(max_length=200)),
                ('description', models.TextField(blank=True, default='')),
                ('author_id', models.UUIDField(blank=True, null=True)),
                ('is_published', models.BooleanField(default=False)),
                ('department', models.CharField(blank=True, max_length=120, null=True)),
                ('tags', models.JSONField(default=list)),
                ('is_deleted', models.BooleanField(default=False)),
            ],
            options={'db_table': 'lms_learning_paths', 'ordering': ['-created_at']},
        ),
        migrations.CreateModel(
            name='LearningPathCourse',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True)),
                ('path', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='path_courses', to='lms.learningpath')),
                ('course', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='path_memberships', to='lms.course')),
                ('order', models.PositiveIntegerField(default=0)),
            ],
            options={'db_table': 'lms_learning_path_courses', 'ordering': ['order']},
        ),
        migrations.AddConstraint(
            model_name='learningpathcourse',
            constraint=models.UniqueConstraint(
                fields=['path', 'course'], name='lms_pathcourse_uniq'),
        ),
        migrations.CreateModel(
            name='CourseEnrollment',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('tenant_id', models.UUIDField(db_index=True, null=True, blank=True)),
                ('company_id', models.UUIDField(db_index=True, null=True, blank=True)),
                ('course', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='enrollments', to='lms.course')),
                ('employee_id', models.UUIDField(db_index=True)),
                ('status', models.CharField(
                    choices=[('enrolled', 'Enrolled'), ('in_progress', 'In Progress'),
                             ('completed', 'Completed'), ('dropped', 'Dropped')],
                    default='enrolled', max_length=20)),
                ('enrolled_at', models.DateTimeField(auto_now_add=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('score', models.FloatField(blank=True, null=True)),
                ('progress_pct', models.FloatField(default=0.0)),
            ],
            options={'db_table': 'lms_course_enrollments'},
        ),
        migrations.AddConstraint(
            model_name='courseenrollment',
            constraint=models.UniqueConstraint(
                fields=['course', 'employee_id'], name='lms_enroll_course_emp_uniq'),
        ),
        migrations.AddIndex(
            model_name='courseenrollment',
            index=models.Index(
                fields=['company_id', 'employee_id'], name='lms_enroll_co_emp_idx'),
        ),
        migrations.CreateModel(
            name='LessonProgress',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True)),
                ('enrollment', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='lesson_progress', to='lms.courseenrollment')),
                ('lesson', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE, to='lms.lesson')),
                ('completed', models.BooleanField(default=False)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('time_spent_s', models.PositiveIntegerField(default=0)),
            ],
            options={'db_table': 'lms_lesson_progress'},
        ),
        migrations.AddConstraint(
            model_name='lessonprogress',
            constraint=models.UniqueConstraint(
                fields=['enrollment', 'lesson'], name='lms_lessonprog_enr_les_uniq'),
        ),
        migrations.CreateModel(
            name='AssessmentAttempt',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('tenant_id', models.UUIDField(db_index=True, null=True, blank=True)),
                ('company_id', models.UUIDField(db_index=True, null=True, blank=True)),
                ('enrollment', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='attempts', to='lms.courseenrollment')),
                ('assessment', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE, to='lms.assessment')),
                ('attempt_no', models.PositiveIntegerField(default=1)),
                ('score', models.FloatField()),
                ('passed', models.BooleanField()),
                ('answers', models.JSONField(default=dict)),
                ('submitted_at', models.DateTimeField(blank=True, null=True)),
            ],
            options={'db_table': 'lms_assessment_attempts'},
        ),
        migrations.AddIndex(
            model_name='assessmentattempt',
            index=models.Index(
                fields=['company_id', 'enrollment_id'], name='lms_attempt_co_enr_idx'),
        ),
        migrations.CreateModel(
            name='CourseCertificate',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('tenant_id', models.UUIDField(db_index=True, null=True, blank=True)),
                ('company_id', models.UUIDField(db_index=True, null=True, blank=True)),
                ('enrollment', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='certificate', to='lms.courseenrollment')),
                ('certificate_no', models.CharField(max_length=40, unique=True)),
                ('issued_at', models.DateTimeField(auto_now_add=True)),
                ('expires_at', models.DateTimeField(blank=True, null=True)),
                ('pdf_url', models.TextField(blank=True, null=True)),
            ],
            options={'db_table': 'lms_course_certificates'},
        ),
    ]
