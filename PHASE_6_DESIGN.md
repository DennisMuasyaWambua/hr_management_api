# Phase 6 Design — Learning Management System (LMS)

**Date:** 2026-06-24

---

## Scope

Build a structured self-paced LMS in a new `apps/lms/` app, complementing the existing event-based training sessions in `apps/hr/` (which are not changed). The LMS handles: course authoring, module/lesson structure, assessments, learning paths, enrolment, progress tracking, and certificates.

---

## Data Model

### 1. Course

```python
class Course(TenantStamped):
    STATUS = [('draft','Draft'),('published','Published'),('archived','Archived')]
    LEVEL  = [('beginner','Beginner'),('intermediate','Intermediate'),('advanced','Advanced')]

    title          CharField(200)
    description    TextField(blank=True)
    level          CharField(20, choices=LEVEL, default='beginner')
    status         CharField(20, choices=STATUS, default='draft')
    thumbnail_url  TextField(null=True)
    author_id      UUIDField(null=True)          # HR/admin who created
    duration_hours FloatField(default=0)         # estimated time
    is_mandatory   BooleanField(default=False)
    department     CharField(120, null=True)     # optional targeting
    tags           JSONField(default=list)
    pass_score     FloatField(default=70.0)      # % to earn certificate
    is_deleted     BooleanField(default=False)

    db_table = 'lms_courses'
```

### 2. CourseModule

```python
class CourseModule(TenantStamped):
    course      ForeignKey(Course, related_name='modules')
    title       CharField(200)
    description TextField(blank=True)
    order       PositiveIntegerField(default=0)
    is_deleted  BooleanField(default=False)

    db_table = 'lms_course_modules'
    ordering = ['order']
    unique_together = [('course', 'order')]   # no duplicate ordinals per course
```

### 3. Lesson

```python
class Lesson(TenantStamped):
    TYPE = [('text','Text'),('video','Video'),('file','File'),('quiz','Quiz'),('scorm','SCORM')]

    module         ForeignKey(CourseModule, related_name='lessons')
    title          CharField(200)
    lesson_type    CharField(20, choices=TYPE, default='text')
    content        TextField(blank=True)       # markdown body (text lessons)
    video_url      TextField(null=True)
    file_url       TextField(null=True)
    duration_mins  PositiveIntegerField(default=0)
    order          PositiveIntegerField(default=0)
    is_deleted     BooleanField(default=False)

    db_table = 'lms_lessons'
    ordering = ['order']
```

### 4. Assessment

```python
class Assessment(TenantStamped):
    course           ForeignKey(Course, related_name='assessments')
    title            CharField(200)
    pass_score       FloatField(default=70.0)
    time_limit_mins  PositiveIntegerField(null=True)  # null = no limit
    max_attempts     PositiveIntegerField(default=3)
    is_deleted       BooleanField(default=False)

    db_table = 'lms_assessments'
```

### 5. AssessmentQuestion

```python
class AssessmentQuestion(TenantStamped):
    TYPE = [('mcq','Multiple Choice'),('true_false','True/False'),('short_answer','Short Answer')]

    assessment   ForeignKey(Assessment, related_name='questions')
    question     TextField()
    question_type CharField(20, choices=TYPE, default='mcq')
    options      JSONField(default=list)   # [{"label":"A","text":"..."}]
    answer       JSONField()               # correct answer(s)
    points       FloatField(default=1.0)
    order        PositiveIntegerField(default=0)

    db_table = 'lms_assessment_questions'
    ordering = ['order']
```

### 6. LearningPath

```python
class LearningPath(TenantStamped):
    title        CharField(200)
    description  TextField(blank=True)
    author_id    UUIDField(null=True)
    is_published BooleanField(default=False)
    department   CharField(120, null=True)
    tags         JSONField(default=list)
    is_deleted   BooleanField(default=False)

    db_table = 'lms_learning_paths'
```

### 7. LearningPathCourse

```python
class LearningPathCourse(models.Model):
    id           UUIDField(PK)
    path         ForeignKey(LearningPath, related_name='path_courses')
    course       ForeignKey(Course)
    order        PositiveIntegerField(default=0)

    db_table = 'lms_learning_path_courses'
    unique_together = [('path', 'course')]
    ordering = ['order']
```

### 8. CourseEnrollment

```python
class CourseEnrollment(TenantStamped):
    STATUS = [('enrolled','Enrolled'),('in_progress','In Progress'),
              ('completed','Completed'),('dropped','Dropped')]

    course        ForeignKey(Course)
    employee_id   UUIDField(db_index=True)
    status        CharField(20, choices=STATUS, default='enrolled')
    enrolled_at   DateTimeField(auto_now_add=True)
    completed_at  DateTimeField(null=True)
    score         FloatField(null=True)          # from final assessment
    progress_pct  FloatField(default=0.0)        # computed: lessons_done / total

    db_table = 'lms_course_enrollments'
    unique_together = [('course', 'employee_id')]
```

### 9. LessonProgress

```python
class LessonProgress(models.Model):
    id           UUIDField(PK)
    enrollment   ForeignKey(CourseEnrollment, related_name='lesson_progress')
    lesson       ForeignKey(Lesson)
    completed    BooleanField(default=False)
    completed_at DateTimeField(null=True)
    time_spent_s PositiveIntegerField(default=0)

    db_table = 'lms_lesson_progress'
    unique_together = [('enrollment', 'lesson')]
```

### 10. AssessmentAttempt

```python
class AssessmentAttempt(TenantStamped):
    enrollment   ForeignKey(CourseEnrollment, related_name='attempts')
    assessment   ForeignKey(Assessment)
    attempt_no   PositiveIntegerField(default=1)
    score        FloatField()
    passed       BooleanField()
    answers      JSONField(default=dict)    # {question_id: answer}
    started_at   DateTimeField(auto_now_add=True)
    submitted_at DateTimeField(null=True)

    db_table = 'lms_assessment_attempts'
```

### 11. CourseCertificate

```python
class CourseCertificate(TenantStamped):
    enrollment     OneToOneField(CourseEnrollment, related_name='certificate')
    certificate_no CharField(40, unique=True)   # auto-generated
    issued_at      DateTimeField(auto_now_add=True)
    expires_at     DateTimeField(null=True)
    pdf_url        TextField(null=True)

    db_table = 'lms_course_certificates'
```

---

## Endpoints

All require `lms.view` or `lms.manage`.

### Course Catalogue (HR-authored)
| Method | URL | Description |
|--------|-----|-------------|
| GET/POST | `/api/lms/courses/` | List / create courses |
| GET/PATCH/DELETE | `/api/lms/courses/{id}/` | Detail / update / soft-delete |
| GET/POST | `/api/lms/courses/{id}/modules/` | List / add modules |
| GET/PATCH/DELETE | `/api/lms/modules/{id}/` | Module detail |
| GET/POST | `/api/lms/modules/{id}/lessons/` | List / add lessons |
| GET/PATCH/DELETE | `/api/lms/lessons/{id}/` | Lesson detail |
| GET/POST | `/api/lms/courses/{id}/assessments/` | Assessments for a course |
| GET/PATCH/DELETE | `/api/lms/assessments/{id}/` | Assessment detail |
| GET/POST | `/api/lms/assessments/{id}/questions/` | Questions |

### Learning Paths
| Method | URL | Description |
|--------|-----|-------------|
| GET/POST | `/api/lms/learning-paths/` | List / create |
| GET/PATCH/DELETE | `/api/lms/learning-paths/{id}/` | Detail |
| POST | `/api/lms/learning-paths/{id}/add-course/` | Add course to path |
| DELETE | `/api/lms/learning-paths/{id}/remove-course/` | Remove course |

### Learner Endpoints
| Method | URL | Description |
|--------|-----|-------------|
| GET/POST | `/api/lms/enrollments/` | My enrolments / enrol in a course |
| GET | `/api/lms/enrollments/{id}/` | Enrolment detail + progress |
| POST | `/api/lms/enrollments/{id}/complete-lesson/` | Mark lesson complete |
| GET/POST | `/api/lms/enrollments/{id}/submit-assessment/` | Submit assessment attempt |
| GET | `/api/lms/certificates/` | My certificates |
| GET | `/api/lms/certificates/{id}/` | Certificate detail |

---

## RBAC

New module: `lms`. Grants in a new Core migration `0014_lms_rbac`:
- `super_admin`, `company_admin` → `lms.view + lms.manage`
- `internal_hr`, `deployed_hr`, `hr` → `lms.view + lms.manage`
- `internal_manager`, `deployed_manager`, `manager` → `lms.view`
- `white_collar_employee`, `blue_collar_employee`, `employee` → `lms.view`

---

## Key Design Decisions

1. **Separate app** — LMS is self-contained in `apps/lms/`. No changes to `apps/hr/` training models; they handle instructor-led events, LMS handles self-paced content.

2. **Progress auto-update** — `LessonProgress` completion triggers `CourseEnrollment.progress_pct` recomputation via a signal or inside the `complete-lesson` action.

3. **Certificate auto-issue** — When enrolment reaches `completed` status (100% lessons done AND assessment score ≥ `pass_score`), a `CourseCertificate` is auto-created with a unique `certificate_no`.

4. **Assessment auto-grade** — MCQ and True/False questions are auto-graded server-side. Short-answer questions store the answer and require manual review (flagged in `AssessmentAttempt`).

5. **Ordering** — `CourseModule.order` and `Lesson.order` enforce sequence. Both have `unique_together` with parent to prevent gaps being structural requirement.

---

## Migration Plan

1. `apps/lms/migrations/0001_initial.py` — all 11 models
2. `apps/core/migrations/0014_lms_rbac.py` — lms permissions

---

## Test Plan (target ≥ 45 tests)

| Class | Tests |
|-------|-------|
| TestCourseCRUD | create, list, detail, update, soft-delete, RBAC 401 |
| TestModuleLessonCRUD | add module, add lesson, order enforced |
| TestAssessmentCRUD | create assessment, add questions |
| TestLearningPath | create, add/remove course, order |
| TestEnrollment | enrol, duplicate rejected, progress tracking |
| TestLessonCompletion | mark complete, progress_pct updates |
| TestAssessmentSubmit | MCQ auto-grade, pass → certificate issued, fail → no cert, max attempts |
| TestCertificate | list, detail, unique number |
