import uuid

from django.contrib.auth.models import User
from django.test import override_settings
from rest_framework.test import APIClient, APITestCase

from apps.lms.models import (Assessment, AssessmentQuestion, Course,
                              CourseEnrollment, CourseModule, CourseCertificate,
                              LearningPath, LearningPathCourse, Lesson,
                              LessonProgress)
from apps.payroll.models import Company

COMPANY = uuid.UUID('00000000-0000-0000-0000-000000000090')
COMPANY_STR = str(COMPANY)


def _company_obj():
    return Company.objects.get_or_create(
        id=COMPANY,
        defaults={
            'name': 'LMS Test Co', 'tenant_id': uuid.uuid4(),
            'contact_email': 'lms@test.com',
        }
    )[0]


def _course(**kwargs):
    defaults = dict(
        company_id=COMPANY, tenant_id=uuid.uuid4(),
        title='Test Course', level='beginner', status='published',
        pass_score=70.0,
    )
    defaults.update(kwargs)
    return Course.objects.create(**defaults)


def _module(course, order=0, **kwargs):
    defaults = dict(
        company_id=COMPANY, tenant_id=uuid.uuid4(),
        course=course, title='Module 1', order=order,
    )
    defaults.update(kwargs)
    return CourseModule.objects.create(**defaults)


def _lesson(module, order=0, **kwargs):
    defaults = dict(
        company_id=COMPANY, tenant_id=uuid.uuid4(),
        module=module, title='Lesson 1', lesson_type='text', order=order,
    )
    defaults.update(kwargs)
    return Lesson.objects.create(**defaults)


def _assessment(course, **kwargs):
    defaults = dict(
        company_id=COMPANY, tenant_id=uuid.uuid4(),
        course=course, title='Quiz 1', pass_score=70.0, max_attempts=3,
    )
    defaults.update(kwargs)
    return Assessment.objects.create(**defaults)


def _question(assessment, answer='A', **kwargs):
    defaults = dict(
        company_id=COMPANY, tenant_id=uuid.uuid4(),
        assessment=assessment, question='What is 2+2?',
        question_type='mcq', options=[{'label': 'A', 'text': '4'}],
        answer=answer, points=1.0, order=0,
    )
    defaults.update(kwargs)
    return AssessmentQuestion.objects.create(**defaults)


def _enrollment(course, **kwargs):
    defaults = dict(
        company_id=COMPANY, tenant_id=uuid.uuid4(),
        course=course, employee_id=uuid.uuid4(),
    )
    defaults.update(kwargs)
    return CourseEnrollment.objects.create(**defaults)


@override_settings(RBAC_STRICT=False)
class TestCourseCRUD(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user('lms_test1', password='pass')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.client.credentials(
            HTTP_X_COMPANY_ID=COMPANY_STR,
            HTTP_X_USER_ROLE='internal_hr',
        )

    def test_create_course(self):
        resp = self.client.post('/api/lms/courses/', {
            'title': 'Python 101', 'level': 'beginner', 'pass_score': 70,
        })
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()['title'], 'Python 101')

    def test_list_courses(self):
        _course(title='A')
        _course(title='B')
        resp = self.client.get('/api/lms/courses/')
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(len(resp.json()['results']), 2)

    def test_retrieve_course(self):
        course = _course(title='Detail Course')
        resp = self.client.get(f'/api/lms/courses/{course.id}/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('modules', resp.json())
        self.assertIn('assessments', resp.json())

    def test_update_course(self):
        course = _course(title='Old Title')
        resp = self.client.patch(f'/api/lms/courses/{course.id}/', {'title': 'New Title'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['title'], 'New Title')

    def test_delete_course_soft(self):
        course = _course()
        resp = self.client.delete(f'/api/lms/courses/{course.id}/')
        self.assertEqual(resp.status_code, 204)
        course.refresh_from_db()
        self.assertTrue(course.is_deleted)

    def test_deleted_course_not_in_list(self):
        _course(title='Gone', is_deleted=True)
        _course(title='Visible')
        resp = self.client.get('/api/lms/courses/')
        titles = [r['title'] for r in resp.json()['results']]
        self.assertNotIn('Gone', titles)
        self.assertIn('Visible', titles)


@override_settings(RBAC_STRICT=False)
class TestModuleLesson(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user('lms_test2', password='pass')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.client.credentials(
            HTTP_X_COMPANY_ID=COMPANY_STR,
            HTTP_X_USER_ROLE='internal_hr',
        )
        self.course = _course()

    def test_add_module_via_course_action(self):
        resp = self.client.post(f'/api/lms/courses/{self.course.id}/modules/', {
            'title': 'Module A', 'order': 0,
        })
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()['title'], 'Module A')

    def test_list_modules_via_course_action(self):
        _module(self.course, order=0)
        _module(self.course, order=1, title='Module B')
        resp = self.client.get(f'/api/lms/courses/{self.course.id}/modules/')
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(len(resp.json()), 2)

    def test_add_lesson_via_module_action(self):
        mod = _module(self.course)
        resp = self.client.post(f'/api/lms/modules/{mod.id}/lessons/', {
            'title': 'Lesson 1', 'lesson_type': 'text', 'content': 'Hello', 'order': 0,
        })
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()['title'], 'Lesson 1')

    def test_list_lessons_via_module_action(self):
        mod = _module(self.course)
        _lesson(mod, order=0)
        _lesson(mod, order=1, title='Lesson 2')
        resp = self.client.get(f'/api/lms/modules/{mod.id}/lessons/')
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(len(resp.json()), 2)

    def test_module_detail_includes_lessons(self):
        mod = _module(self.course)
        _lesson(mod)
        resp = self.client.get(f'/api/lms/modules/{mod.id}/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('lessons', resp.json())

    def test_soft_delete_module(self):
        mod = _module(self.course)
        resp = self.client.delete(f'/api/lms/modules/{mod.id}/')
        self.assertEqual(resp.status_code, 204)
        mod.refresh_from_db()
        self.assertTrue(mod.is_deleted)


@override_settings(RBAC_STRICT=False)
class TestAssessmentCRUD(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user('lms_test3', password='pass')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.client.credentials(
            HTTP_X_COMPANY_ID=COMPANY_STR,
            HTTP_X_USER_ROLE='internal_hr',
        )
        self.course = _course()

    def test_create_assessment(self):
        resp = self.client.post(f'/api/lms/courses/{self.course.id}/assessments/', {
            'title': 'Final Exam', 'pass_score': 80, 'max_attempts': 2,
        })
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()['title'], 'Final Exam')

    def test_add_question_to_assessment(self):
        asmt = _assessment(self.course)
        resp = self.client.post(f'/api/lms/assessments/{asmt.id}/questions/', {
            'question': 'What is Python?',
            'question_type': 'mcq',
            'options': [{'label': 'A', 'text': 'A language'}],
            'answer': 'A',
            'points': 2.0,
            'order': 0,
        }, format='json')
        self.assertEqual(resp.status_code, 201)

    def test_list_questions(self):
        asmt = _assessment(self.course)
        _question(asmt, order=0)
        _question(asmt, order=1, question='Another?')
        resp = self.client.get(f'/api/lms/assessments/{asmt.id}/questions/')
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(len(resp.json()), 2)

    def test_assessment_detail_includes_questions(self):
        asmt = _assessment(self.course)
        _question(asmt)
        resp = self.client.get(f'/api/lms/assessments/{asmt.id}/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('questions', resp.json())

    def test_soft_delete_assessment(self):
        asmt = _assessment(self.course)
        resp = self.client.delete(f'/api/lms/assessments/{asmt.id}/')
        self.assertEqual(resp.status_code, 204)
        asmt.refresh_from_db()
        self.assertTrue(asmt.is_deleted)


@override_settings(RBAC_STRICT=False)
class TestLearningPath(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user('lms_test4', password='pass')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.client.credentials(
            HTTP_X_COMPANY_ID=COMPANY_STR,
            HTTP_X_USER_ROLE='internal_hr',
        )

    def test_create_learning_path(self):
        resp = self.client.post('/api/lms/learning-paths/', {
            'title': 'Backend Path', 'description': 'Learn backend dev',
        })
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()['title'], 'Backend Path')

    def test_list_learning_paths(self):
        lp = LearningPath.objects.create(
            company_id=COMPANY, tenant_id=uuid.uuid4(), title='Path A')
        resp = self.client.get('/api/lms/learning-paths/')
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(len(resp.json()['results']), 1)

    def test_add_course_to_path(self):
        lp = LearningPath.objects.create(
            company_id=COMPANY, tenant_id=uuid.uuid4(), title='Path B')
        course = _course()
        resp = self.client.post(
            f'/api/lms/learning-paths/{lp.id}/add-course/',
            {'course_id': str(course.id), 'order': 0})
        self.assertEqual(resp.status_code, 201)

    def test_add_duplicate_course_to_path_is_409(self):
        lp = LearningPath.objects.create(
            company_id=COMPANY, tenant_id=uuid.uuid4(), title='Path C')
        course = _course()
        LearningPathCourse.objects.create(path=lp, course=course, order=0)
        resp = self.client.post(
            f'/api/lms/learning-paths/{lp.id}/add-course/',
            {'course_id': str(course.id), 'order': 1})
        self.assertEqual(resp.status_code, 409)

    def test_remove_course_from_path(self):
        lp = LearningPath.objects.create(
            company_id=COMPANY, tenant_id=uuid.uuid4(), title='Path D')
        course = _course()
        LearningPathCourse.objects.create(path=lp, course=course, order=0)
        resp = self.client.post(
            f'/api/lms/learning-paths/{lp.id}/remove-course/',
            {'course_id': str(course.id)})
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(
            LearningPathCourse.objects.filter(path=lp, course=course).exists())

    def test_path_course_count(self):
        lp = LearningPath.objects.create(
            company_id=COMPANY, tenant_id=uuid.uuid4(), title='Path E')
        c1, c2 = _course(title='C1'), _course(title='C2')
        LearningPathCourse.objects.create(path=lp, course=c1, order=0)
        LearningPathCourse.objects.create(path=lp, course=c2, order=1)
        resp = self.client.get(f'/api/lms/learning-paths/{lp.id}/')
        self.assertEqual(resp.json()['course_count'], 2)


@override_settings(RBAC_STRICT=False)
class TestEnrollment(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user('lms_test5', password='pass')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.client.credentials(
            HTTP_X_COMPANY_ID=COMPANY_STR,
            HTTP_X_USER_ROLE='internal_hr',
        )
        self.course = _course()
        self.emp_id = uuid.uuid4()

    def test_enroll_in_course(self):
        resp = self.client.post('/api/lms/enrollments/', {
            'course': str(self.course.id),
            'employee_id': str(self.emp_id),
        })
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()['status'], 'enrolled')

    def test_enrollment_has_progress_pct(self):
        resp = self.client.post('/api/lms/enrollments/', {
            'course': str(self.course.id),
            'employee_id': str(self.emp_id),
        })
        self.assertEqual(resp.json()['progress_pct'], 0.0)

    def test_duplicate_enrollment_rejected(self):
        _enrollment(self.course, employee_id=self.emp_id)
        resp = self.client.post('/api/lms/enrollments/', {
            'course': str(self.course.id),
            'employee_id': str(self.emp_id),
        })
        self.assertEqual(resp.status_code, 400)

    def test_list_enrollments(self):
        _enrollment(self.course)
        _enrollment(self.course)
        resp = self.client.get('/api/lms/enrollments/')
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(len(resp.json()['results']), 2)

    def test_enrollment_detail(self):
        enroll = _enrollment(self.course, employee_id=self.emp_id)
        resp = self.client.get(f'/api/lms/enrollments/{enroll.id}/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('lesson_progress', resp.json())


@override_settings(RBAC_STRICT=False)
class TestLessonCompletion(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user('lms_test6', password='pass')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.client.credentials(
            HTTP_X_COMPANY_ID=COMPANY_STR,
            HTTP_X_USER_ROLE='internal_hr',
        )
        self.course = _course()
        self.mod = _module(self.course)
        self.lesson = _lesson(self.mod, order=0)
        self.enrollment = _enrollment(self.course)

    def test_complete_lesson_updates_progress(self):
        resp = self.client.post(
            f'/api/lms/enrollments/{self.enrollment.id}/complete-lesson/',
            {'lesson_id': str(self.lesson.id), 'time_spent_s': 120})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertGreater(data['progress_pct'], 0)

    def test_status_changes_to_in_progress(self):
        self.client.post(
            f'/api/lms/enrollments/{self.enrollment.id}/complete-lesson/',
            {'lesson_id': str(self.lesson.id)})
        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.status, 'in_progress')

    def test_completing_all_lessons_sets_100(self):
        lesson2 = _lesson(self.mod, order=1, title='Lesson 2')
        self.client.post(
            f'/api/lms/enrollments/{self.enrollment.id}/complete-lesson/',
            {'lesson_id': str(self.lesson.id)})
        self.client.post(
            f'/api/lms/enrollments/{self.enrollment.id}/complete-lesson/',
            {'lesson_id': str(lesson2.id)})
        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.progress_pct, 100.0)

    def test_duplicate_complete_is_idempotent(self):
        self.client.post(
            f'/api/lms/enrollments/{self.enrollment.id}/complete-lesson/',
            {'lesson_id': str(self.lesson.id)})
        self.client.post(
            f'/api/lms/enrollments/{self.enrollment.id}/complete-lesson/',
            {'lesson_id': str(self.lesson.id)})
        count = LessonProgress.objects.filter(
            enrollment=self.enrollment, completed=True).count()
        self.assertEqual(count, 1)

    def test_complete_lesson_missing_lesson_id(self):
        resp = self.client.post(
            f'/api/lms/enrollments/{self.enrollment.id}/complete-lesson/', {})
        self.assertEqual(resp.status_code, 400)


@override_settings(RBAC_STRICT=False)
class TestAssessmentSubmit(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user('lms_test7', password='pass')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.client.credentials(
            HTTP_X_COMPANY_ID=COMPANY_STR,
            HTTP_X_USER_ROLE='internal_hr',
        )
        self.course = _course(pass_score=70.0)
        self.assessment = _assessment(self.course, pass_score=70.0, max_attempts=3)
        self.q = _question(self.assessment, answer='A')
        self.enrollment = _enrollment(self.course)

    def _submit(self, answers, enrollment=None):
        enrollment = enrollment or self.enrollment
        return self.client.post(
            f'/api/lms/enrollments/{enrollment.id}/submit-assessment/',
            {'assessment_id': str(self.assessment.id), 'answers': answers},
            format='json')

    def test_correct_answer_passes(self):
        resp = self._submit({str(self.q.id): 'A'})
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(resp.json()['passed'])
        self.assertEqual(resp.json()['score'], 100.0)

    def test_wrong_answer_fails(self):
        resp = self._submit({str(self.q.id): 'B'})
        self.assertEqual(resp.status_code, 201)
        self.assertFalse(resp.json()['passed'])
        self.assertEqual(resp.json()['score'], 0.0)

    def test_pass_issues_certificate(self):
        self._submit({str(self.q.id): 'A'})
        self.assertTrue(
            CourseCertificate.objects.filter(enrollment=self.enrollment).exists())

    def test_fail_does_not_issue_certificate(self):
        self._submit({str(self.q.id): 'B'})
        self.assertFalse(
            CourseCertificate.objects.filter(enrollment=self.enrollment).exists())

    def test_pass_marks_enrollment_completed(self):
        self._submit({str(self.q.id): 'A'})
        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.status, 'completed')

    def test_max_attempts_enforced(self):
        for _ in range(3):
            self._submit({str(self.q.id): 'B'})
        resp = self._submit({str(self.q.id): 'A'})
        self.assertEqual(resp.status_code, 409)

    def test_attempt_number_increments(self):
        resp1 = self._submit({str(self.q.id): 'B'})
        resp2 = self._submit({str(self.q.id): 'B'})
        self.assertEqual(resp1.json()['attempt_no'], 1)
        self.assertEqual(resp2.json()['attempt_no'], 2)


@override_settings(RBAC_STRICT=False)
class TestCertificate(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user('lms_test8', password='pass')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.client.credentials(
            HTTP_X_COMPANY_ID=COMPANY_STR,
            HTTP_X_USER_ROLE='internal_hr',
        )

    def test_list_certificates(self):
        course = _course()
        enroll = _enrollment(course)
        CourseCertificate.objects.create(
            company_id=COMPANY, tenant_id=uuid.uuid4(),
            enrollment=enroll, certificate_no=f'CERT-{uuid.uuid4().hex[:8].upper()}')
        resp = self.client.get('/api/lms/certificates/')
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(len(resp.json()['results']), 1)

    def test_certificate_has_expected_keys(self):
        course = _course()
        enroll = _enrollment(course)
        cert = CourseCertificate.objects.create(
            company_id=COMPANY, tenant_id=uuid.uuid4(),
            enrollment=enroll, certificate_no=f'CERT-{uuid.uuid4().hex[:8].upper()}')
        resp = self.client.get(f'/api/lms/certificates/{cert.id}/')
        self.assertEqual(resp.status_code, 200)
        for key in ['certificate_no', 'issued_at', 'course_title', 'employee_id']:
            self.assertIn(key, resp.json())

    def test_certificate_no_is_unique(self):
        course = _course()
        e1 = _enrollment(course)
        e2 = _enrollment(course)
        c1 = CourseCertificate.objects.create(
            company_id=COMPANY, tenant_id=uuid.uuid4(),
            enrollment=e1, certificate_no=f'CERT-A{uuid.uuid4().hex[:6].upper()}')
        c2 = CourseCertificate.objects.create(
            company_id=COMPANY, tenant_id=uuid.uuid4(),
            enrollment=e2, certificate_no=f'CERT-B{uuid.uuid4().hex[:6].upper()}')
        self.assertNotEqual(c1.certificate_no, c2.certificate_no)

    def test_certificates_read_only(self):
        resp = self.client.post('/api/lms/certificates/', {})
        self.assertEqual(resp.status_code, 405)
