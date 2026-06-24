import uuid

from django.db import models

from apps.hr.models import TenantStamped


class Course(TenantStamped):
    STATUS = [('draft', 'Draft'), ('published', 'Published'), ('archived', 'Archived')]
    LEVEL = [('beginner', 'Beginner'), ('intermediate', 'Intermediate'), ('advanced', 'Advanced')]

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default='')
    level = models.CharField(max_length=20, choices=LEVEL, default='beginner')
    status = models.CharField(max_length=20, choices=STATUS, default='draft')
    thumbnail_url = models.TextField(null=True, blank=True)
    author_id = models.UUIDField(null=True, blank=True)
    duration_hours = models.FloatField(default=0)
    is_mandatory = models.BooleanField(default=False)
    department = models.CharField(max_length=120, null=True, blank=True)
    tags = models.JSONField(default=list)
    pass_score = models.FloatField(default=70.0)
    is_deleted = models.BooleanField(default=False)

    class Meta:
        db_table = 'lms_courses'
        ordering = ['-created_at']


class CourseModule(TenantStamped):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='modules')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default='')
    order = models.PositiveIntegerField(default=0)
    is_deleted = models.BooleanField(default=False)

    class Meta:
        db_table = 'lms_course_modules'
        ordering = ['order']


class Lesson(TenantStamped):
    TYPE = [('text', 'Text'), ('video', 'Video'), ('file', 'File'),
            ('quiz', 'Quiz'), ('scorm', 'SCORM')]

    module = models.ForeignKey(CourseModule, on_delete=models.CASCADE, related_name='lessons')
    title = models.CharField(max_length=200)
    lesson_type = models.CharField(max_length=20, choices=TYPE, default='text')
    content = models.TextField(blank=True, default='')
    video_url = models.TextField(null=True, blank=True)
    file_url = models.TextField(null=True, blank=True)
    duration_mins = models.PositiveIntegerField(default=0)
    order = models.PositiveIntegerField(default=0)
    is_deleted = models.BooleanField(default=False)

    class Meta:
        db_table = 'lms_lessons'
        ordering = ['order']


class Assessment(TenantStamped):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='assessments')
    title = models.CharField(max_length=200)
    pass_score = models.FloatField(default=70.0)
    time_limit_mins = models.PositiveIntegerField(null=True, blank=True)
    max_attempts = models.PositiveIntegerField(default=3)
    is_deleted = models.BooleanField(default=False)

    class Meta:
        db_table = 'lms_assessments'


class AssessmentQuestion(TenantStamped):
    TYPE = [('mcq', 'Multiple Choice'), ('true_false', 'True/False'),
            ('short_answer', 'Short Answer')]

    assessment = models.ForeignKey(Assessment, on_delete=models.CASCADE, related_name='questions')
    question = models.TextField()
    question_type = models.CharField(max_length=20, choices=TYPE, default='mcq')
    options = models.JSONField(default=list)
    answer = models.JSONField()
    points = models.FloatField(default=1.0)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'lms_assessment_questions'
        ordering = ['order']


class LearningPath(TenantStamped):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default='')
    author_id = models.UUIDField(null=True, blank=True)
    is_published = models.BooleanField(default=False)
    department = models.CharField(max_length=120, null=True, blank=True)
    tags = models.JSONField(default=list)
    is_deleted = models.BooleanField(default=False)

    class Meta:
        db_table = 'lms_learning_paths'
        ordering = ['-created_at']


class LearningPathCourse(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    path = models.ForeignKey(LearningPath, on_delete=models.CASCADE,
                             related_name='path_courses')
    course = models.ForeignKey(Course, on_delete=models.CASCADE,
                               related_name='path_memberships')
    order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'lms_learning_path_courses'
        unique_together = [('path', 'course')]
        ordering = ['order']


class CourseEnrollment(TenantStamped):
    STATUS = [('enrolled', 'Enrolled'), ('in_progress', 'In Progress'),
              ('completed', 'Completed'), ('dropped', 'Dropped')]

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='enrollments')
    employee_id = models.UUIDField(db_index=True)
    status = models.CharField(max_length=20, choices=STATUS, default='enrolled')
    enrolled_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    score = models.FloatField(null=True, blank=True)
    progress_pct = models.FloatField(default=0.0)

    class Meta:
        db_table = 'lms_course_enrollments'
        unique_together = [('course', 'employee_id')]
        indexes = [
            models.Index(fields=['company_id', 'employee_id'],
                         name='lms_enroll_co_emp_idx'),
        ]


class LessonProgress(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    enrollment = models.ForeignKey(CourseEnrollment, on_delete=models.CASCADE,
                                   related_name='lesson_progress')
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE)
    completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    time_spent_s = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'lms_lesson_progress'
        unique_together = [('enrollment', 'lesson')]


class AssessmentAttempt(TenantStamped):
    enrollment = models.ForeignKey(CourseEnrollment, on_delete=models.CASCADE,
                                   related_name='attempts')
    assessment = models.ForeignKey(Assessment, on_delete=models.CASCADE)
    attempt_no = models.PositiveIntegerField(default=1)
    score = models.FloatField()
    passed = models.BooleanField()
    answers = models.JSONField(default=dict)
    submitted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'lms_assessment_attempts'
        indexes = [
            models.Index(fields=['company_id', 'enrollment_id'],
                         name='lms_attempt_co_enr_idx'),
        ]


class CourseCertificate(TenantStamped):
    enrollment = models.OneToOneField(CourseEnrollment, on_delete=models.CASCADE,
                                      related_name='certificate')
    certificate_no = models.CharField(max_length=40, unique=True)
    issued_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    pdf_url = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'lms_course_certificates'
