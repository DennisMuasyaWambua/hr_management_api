# Phase 6 Implementation Report — Learning Management System (LMS)

**Date:** 2026-06-24  
**Status:** Complete — 44/44 tests passing

---

## Overview

Phase 6 delivers a structured self-paced LMS in `apps/lms/`. It complements the existing event-based `TrainingSession`/`TrainingEnrollment` models in `apps/hr/` (which are unchanged). The LMS handles course authoring with module/lesson hierarchy, assessments with auto-grading, learning paths, enrolment tracking with progress, and automatic certificate issuance on course completion.

---

## Files Delivered

### New Files

| File | Purpose |
|------|---------|
| `apps/lms/__init__.py` | Package marker |
| `apps/lms/apps.py` | `LmsConfig`, label='lms' |
| `apps/lms/models.py` | 11 models |
| `apps/lms/serializers.py` | 12 serializers |
| `apps/lms/views.py` | 7 ViewSets with nested actions |
| `apps/lms/urls.py` | 7 DefaultRouter registrations |
| `apps/lms/migrations/0001_initial.py` | All 11 models |
| `apps/lms/migrations/__init__.py` | Package marker |
| `apps/lms/tests/test_lms.py` | 44 tests across 8 classes |
| `apps/lms/tests/__init__.py` | Package marker |
| `apps/core/migrations/0014_lms_rbac.py` | Grants `lms.view/manage` |

### Modified Files

| File | Change |
|------|--------|
| `hr_api/settings.py` | Added `apps.lms` to `INSTALLED_APPS` |
| `hr_api/urls.py` | Added `path('api/', include('apps.lms.urls'))` |
| `apps/core/management/commands/seed_rbac.py` | Added `'lms'` module + grants to `_HR_GRANTS`, `_MANAGER_GRANTS`, `_EMPLOYEE_GRANTS` |

---

## Models (11 total)

| Model | db_table | Key Features |
|-------|----------|--------------|
| `Course` | `lms_courses` | soft-delete, status (draft/published/archived), pass_score, tags JSONField |
| `CourseModule` | `lms_course_modules` | ordered sections within a course |
| `Lesson` | `lms_lessons` | types: text/video/file/quiz/scorm; ordered within module |
| `Assessment` | `lms_assessments` | per-course quiz; max_attempts, pass_score |
| `AssessmentQuestion` | `lms_assessment_questions` | MCQ/true_false/short_answer; options + answer as JSON |
| `LearningPath` | `lms_learning_paths` | curated course sequences |
| `LearningPathCourse` | `lms_learning_path_courses` | path ↔ course M2M with ordering |
| `CourseEnrollment` | `lms_course_enrollments` | progress_pct, status lifecycle, unique per employee+course |
| `LessonProgress` | `lms_lesson_progress` | per-lesson completion tracking |
| `AssessmentAttempt` | `lms_assessment_attempts` | stores score, passed, answers JSON |
| `CourseCertificate` | `lms_course_certificates` | auto-issued on pass; unique `certificate_no` |

---

## Endpoints

All require `lms.view` (GET) or `lms.manage` (write).

| Method | URL | Description |
|--------|-----|-------------|
| GET/POST | `/api/lms/courses/` | List / create courses |
| GET/PATCH/DELETE | `/api/lms/courses/{id}/` | Detail (includes modules + assessments) / soft-delete |
| GET/POST | `/api/lms/courses/{id}/modules/` | List / add modules |
| GET/PATCH/DELETE | `/api/lms/modules/{id}/` | Module detail (includes lessons) |
| GET/POST | `/api/lms/modules/{id}/lessons/` | List / add lessons |
| GET/PATCH/DELETE | `/api/lms/lessons/{id}/` | Lesson detail |
| GET/POST | `/api/lms/courses/{id}/assessments/` | List / create assessments |
| GET/PATCH/DELETE | `/api/lms/assessments/{id}/` | Assessment detail (includes questions) |
| GET/POST | `/api/lms/assessments/{id}/questions/` | List / add questions |
| GET/POST | `/api/lms/learning-paths/` | List / create paths |
| GET/PATCH/DELETE | `/api/lms/learning-paths/{id}/` | Path detail (includes courses) |
| POST | `/api/lms/learning-paths/{id}/add-course/` | Add course (409 if duplicate) |
| POST | `/api/lms/learning-paths/{id}/remove-course/` | Remove course |
| GET/POST | `/api/lms/enrollments/` | List / enrol |
| GET | `/api/lms/enrollments/{id}/` | Detail with lesson_progress + certificate |
| POST | `/api/lms/enrollments/{id}/complete-lesson/` | Mark lesson done; updates progress_pct |
| POST | `/api/lms/enrollments/{id}/submit-assessment/` | Auto-grade; issues cert on pass |
| GET | `/api/lms/certificates/` | List certificates (read-only) |
| GET | `/api/lms/certificates/{id}/` | Certificate detail |

---

## Key Business Logic

**Progress tracking:** `complete-lesson` upserts a `LessonProgress` record, then recomputes `CourseEnrollment.progress_pct = done_lessons / total_lessons * 100`. Status transitions from `enrolled` → `in_progress` on first lesson.

**Auto-grading:** MCQ and true/false answers compared against stored `AssessmentQuestion.answer`. Short-answer questions store the response for manual review. Score = `earned_points / total_points * 100`.

**Certificate issuance:** Triggered automatically when assessment is passed. `certificate_no` is `CERT-{enroll_id[:8]}-{random[:4]}`. `CourseCertificateViewSet` is read-only (405 on POST).

**Max attempts:** Enforced in `submit-assessment`; returns 409 once `max_attempts` is reached.

---

## Issues Resolved

1. **`unique_together` + `required=False` FK** — `CourseModuleWriteSerializer` had `course` as `required=False` but the model's `unique_together = [('course', 'order')]` caused DRF to add a `UniqueTogetherValidator` that failed when `course` wasn't in the POST body. Fix: removed `unique_together` from the model Meta — the `UniqueConstraint` in the migration still enforces uniqueness at the DB level.

2. **Nested dict in multipart POST** — `answers` (a dict) and `options` (a list of dicts) can't be encoded by DRF's multipart form encoder. Fix: `format='json'` on the affected test calls.

3. **FK fields required in action serializers** — Parent FK (`course`, `module`, `assessment`) were required by serializer validation even though they're injected server-side via `.save()`. Fix: `extra_kwargs = {'field': {'required': False}}` on all four serializers.

---

## RBAC Grants

| Role | Grants |
|------|--------|
| super_admin, company_admin | `lms.view` + `lms.manage` |
| internal_hr, deployed_hr, hr | `lms.view` + `lms.manage` |
| internal_manager, deployed_manager, manager | `lms.view` |
| white_collar_employee, blue_collar_employee, employee | `lms.view` |

---

## Test Coverage

```
TestCourseCRUD              6 tests  — create, list, detail, update, soft-delete, filtered list
TestModuleLesson            6 tests  — add module, list modules, add lesson, list lessons, detail, soft-delete
TestAssessmentCRUD          5 tests  — create, add question, list questions, detail, soft-delete
TestLearningPath            6 tests  — create, list, add course, duplicate 409, remove, course_count
TestEnrollment              5 tests  — enrol, progress_pct, duplicate rejected, list, detail
TestLessonCompletion        5 tests  — progress update, status change, 100%, idempotent, missing id 400
TestAssessmentSubmit        7 tests  — pass/fail grade, cert issued/not issued, status completed, max attempts, attempt_no
TestCertificate             4 tests  — list, keys, unique no, read-only

Total: 44/44 passing
```
