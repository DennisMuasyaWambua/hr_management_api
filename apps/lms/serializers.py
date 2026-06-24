from rest_framework import serializers

from .models import (Assessment, AssessmentAttempt, AssessmentQuestion,
                     Course, CourseEnrollment, CourseModule, CourseCertificate,
                     LearningPath, LearningPathCourse, Lesson, LessonProgress)


class LessonSerializer(serializers.ModelSerializer):
    class Meta:
        model = Lesson
        fields = ['id', 'module', 'title', 'lesson_type', 'content',
                  'video_url', 'file_url', 'duration_mins', 'order',
                  'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']
        extra_kwargs = {'module': {'required': False}}


class CourseModuleSerializer(serializers.ModelSerializer):
    lessons = LessonSerializer(many=True, read_only=True)

    class Meta:
        model = CourseModule
        fields = ['id', 'course', 'title', 'description', 'order',
                  'lessons', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class CourseModuleWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = CourseModule
        fields = ['id', 'course', 'title', 'description', 'order']
        read_only_fields = ['id']
        extra_kwargs = {'course': {'required': False}}


class AssessmentQuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssessmentQuestion
        fields = ['id', 'assessment', 'question', 'question_type',
                  'options', 'answer', 'points', 'order',
                  'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']
        extra_kwargs = {'assessment': {'required': False}}


class AssessmentSerializer(serializers.ModelSerializer):
    questions = AssessmentQuestionSerializer(many=True, read_only=True)

    class Meta:
        model = Assessment
        fields = ['id', 'course', 'title', 'pass_score', 'time_limit_mins',
                  'max_attempts', 'questions', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class AssessmentWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Assessment
        fields = ['id', 'course', 'title', 'pass_score', 'time_limit_mins',
                  'max_attempts']
        read_only_fields = ['id']
        extra_kwargs = {'course': {'required': False}}


class CourseListSerializer(serializers.ModelSerializer):
    module_count = serializers.SerializerMethodField()

    class Meta:
        model = Course
        fields = ['id', 'title', 'description', 'level', 'status',
                  'thumbnail_url', 'duration_hours', 'is_mandatory',
                  'department', 'tags', 'pass_score', 'module_count',
                  'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_module_count(self, obj):
        return obj.modules.filter(is_deleted=False).count()


class CourseDetailSerializer(CourseListSerializer):
    modules = CourseModuleSerializer(many=True, read_only=True)
    assessments = AssessmentSerializer(many=True, read_only=True)

    class Meta(CourseListSerializer.Meta):
        fields = CourseListSerializer.Meta.fields + ['modules', 'assessments']


class LearningPathCourseSerializer(serializers.ModelSerializer):
    course_title = serializers.CharField(source='course.title', read_only=True)
    course_status = serializers.CharField(source='course.status', read_only=True)

    class Meta:
        model = LearningPathCourse
        fields = ['id', 'path', 'course', 'course_title', 'course_status', 'order']
        read_only_fields = ['id']


class LearningPathSerializer(serializers.ModelSerializer):
    path_courses = LearningPathCourseSerializer(many=True, read_only=True)
    course_count = serializers.SerializerMethodField()

    class Meta:
        model = LearningPath
        fields = ['id', 'title', 'description', 'is_published', 'department',
                  'tags', 'course_count', 'path_courses', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_course_count(self, obj):
        return obj.path_courses.count()


class LessonProgressSerializer(serializers.ModelSerializer):
    lesson_title = serializers.CharField(source='lesson.title', read_only=True)

    class Meta:
        model = LessonProgress
        fields = ['id', 'lesson', 'lesson_title', 'completed', 'completed_at',
                  'time_spent_s']
        read_only_fields = ['id', 'completed_at']


class CourseCertificateSerializer(serializers.ModelSerializer):
    course_title = serializers.CharField(source='enrollment.course.title', read_only=True)
    employee_id = serializers.UUIDField(source='enrollment.employee_id', read_only=True)

    class Meta:
        model = CourseCertificate
        fields = ['id', 'enrollment', 'certificate_no', 'issued_at',
                  'expires_at', 'pdf_url', 'course_title', 'employee_id',
                  'created_at', 'updated_at']
        read_only_fields = ['id', 'certificate_no', 'issued_at', 'created_at', 'updated_at']


class AssessmentAttemptSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssessmentAttempt
        fields = ['id', 'enrollment', 'assessment', 'attempt_no', 'score',
                  'passed', 'answers', 'submitted_at', 'created_at']
        read_only_fields = ['id', 'attempt_no', 'score', 'passed',
                            'submitted_at', 'created_at']


class CourseEnrollmentSerializer(serializers.ModelSerializer):
    course_title = serializers.CharField(source='course.title', read_only=True)
    lesson_progress = LessonProgressSerializer(many=True, read_only=True)
    certificate = CourseCertificateSerializer(read_only=True)

    class Meta:
        model = CourseEnrollment
        fields = ['id', 'course', 'course_title', 'employee_id', 'status',
                  'enrolled_at', 'completed_at', 'score', 'progress_pct',
                  'lesson_progress', 'certificate', 'created_at', 'updated_at']
        read_only_fields = ['id', 'employee_id', 'status', 'enrolled_at',
                            'completed_at', 'score', 'progress_pct',
                            'created_at', 'updated_at']
