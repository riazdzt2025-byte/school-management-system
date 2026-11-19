"""The teacher's own login: their classes, their marks, their corrections.

The promise this file protects: **a teacher enters data only for their own
classes, and can never approve their own correction application.** So the tests
come in four groups:

1. Access — a login gains the Teacher department by being linked to an active
   Employee row, and loses it when the employee is resigned.
2. Scope — the class roll, the subjects and the exams are narrowed to the
   teacher's own assignments, and nothing of another institution leaks.
3. Marks entry — a teacher may open their own paper and is turned away from
   every other one, including by typing the URL.
4. Corrections — a teacher checks and submits, never approves or rejects, and
   cannot read an application about a student outside their class.
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import (
    Employee, Exam, ExamMark, Institution, InstitutionAccess,
    MarkCorrectionRequest, Student, Subject, SubjectRequirement, TeacherAssignment,
)
from .permissions import ensure_default_groups, sync_user_department_permissions
from .teacher_scope import (
    current_teaching_session, is_teacher_account, teacher_employee,
    teacher_exams, teacher_students, teacher_subjects,
)


class TeacherBase(TestCase):
    def setUp(self):
        self.institution = Institution.objects.create(
            name='Teacher School', classes='9,10', number=4,
        )
        self.other_institution = Institution.objects.create(
            name='Elsewhere School', classes='9', number=5,
        )
        self.math = Subject.objects.create(
            code='MATH', name='Mathematics', full_marks=100,
            cq_marks=70, mcq_marks=30, pass_percentage=33,
        )
        self.english = Subject.objects.create(
            code='ENG', name='English', full_marks=100,
            cq_marks=70, mcq_marks=30, pass_percentage=33,
        )
        for subject in (self.math, self.english):
            SubjectRequirement.objects.create(
                institution=self.institution, admission_class='9', subject=subject,
            )
        self.my_student = Student.objects.create(
            institution=self.institution, student_id='TH001', name='Rahim Uddin',
            admission_class='9', section='A', roll_no=1, admission_year=2026,
            group='SCI', religion='Islam', guardian_contact_no='01812345678',
        )
        self.other_class_student = Student.objects.create(
            institution=self.institution, student_id='TH002', name='Karim Mia',
            admission_class='10', section='A', roll_no=2, admission_year=2026,
            group='SCI', religion='Islam', guardian_contact_no='01812345679',
        )
        self.foreign_student = Student.objects.create(
            institution=self.other_institution, student_id='TH003', name='Abdul Karim',
            admission_class='9', section='A', roll_no=3, admission_year=2026,
            group='SCI', religion='Islam', guardian_contact_no='01812345680',
        )
        self.exam = Exam.objects.create(
            institution=self.institution, name='First Term 2026',
            exam_type='FIRST_TERM', admission_class='9', session='2026-2027',
            is_published=True,
        )
        self.other_exam = Exam.objects.create(
            institution=self.institution, name='First Term 2026 Class 10',
            exam_type='FIRST_TERM', admission_class='10', session='2026-2027',
            is_published=True,
        )
        ensure_default_groups()
        self.login = get_user_model().objects.create_user(
            username='teacher', password='password',
        )
        self.employee = Employee.objects.create(
            name='Teacher One', designation='Assistant Teacher',
            department='Science', institution=self.institution,
            join_date=date(2020, 1, 1), user=self.login,
        )
        self.assignment = TeacherAssignment.objects.create(
            institution=self.institution, employee=self.employee,
            admission_class='9', section='A', subject=self.math,
            session=current_teaching_session(self.employee) or '2026-2027',
            created_by=self.login,
        )
        self.mark = ExamMark.objects.create(
            exam=self.exam, student=self.my_student, subject=self.math,
            cq_obtained=Decimal('40'), mcq_obtained=Decimal('20'),
            marks_obtained=Decimal('60'),
        )
        self.exam_dept = get_user_model().objects.create_user(
            username='exam-dept', password='password',
        )
        InstitutionAccess.objects.create(
            user=self.exam_dept, institution=self.institution, department='Exam',
        )
        sync_user_department_permissions(self.exam_dept)

    def sign_in(self, department='Teacher'):
        """Sign in the way the app does: access row, groups, then the session.

        The real login persists the Teacher access row and mirrors it into the
        permission group; doing the same here means the tests exercise the same
        permissions the running site would hand the teacher.
        """
        InstitutionAccess.objects.get_or_create(
            user=self.login, institution=self.institution, department=department,
        )
        sync_user_department_permissions(self.login)
        self.client.force_login(self.login)
        session = self.client.session
        session['selected_institution_id'] = self.institution.pk
        session['selected_department'] = department
        session.save()

    def file_request(self, student=None, subject=None, requested_cq='55'):
        """An office-filed draft, built directly (filing is covered elsewhere)."""
        return MarkCorrectionRequest.objects.create(
            institution=self.institution,
            student=student or self.my_student,
            exam=self.exam,
            subject=subject or self.math,
            admission_class=(student or self.my_student).admission_class,
            section=(student or self.my_student).section or '',
            reason='CQ 3 was left unmarked',
            current_parts={'cq': '40.00', 'mcq': '20.00'},
            current_total=Decimal('60'),
            requested_parts={'cq': requested_cq, 'mcq': '20'},
            requested_total=Decimal(requested_cq) + 20,
            filed_by=self.exam_dept,
        )


class TeacherAccessTests(TeacherBase):
    def test_linking_the_employee_row_is_what_makes_a_teacher(self):
        self.assertTrue(is_teacher_account(self.login))
        self.assertEqual(teacher_employee(self.login), self.employee)

    def test_a_resigned_teacher_keeps_no_scope(self):
        self.employee.status = 'RESIGNED'
        self.employee.save(update_fields=['status'])
        self.assertIsNone(teacher_employee(self.login))
        self.assertFalse(
            teacher_students(self.employee).filter(pk=self.my_student.pk).exists()
        )

    def test_an_osd_teacher_keeps_no_scope(self):
        self.employee.status = 'OSD'
        self.employee.save(update_fields=['status'])
        self.assertIsNone(teacher_employee(self.login))

    def test_staff_and_superusers_are_never_narrowed(self):
        self.login.is_staff = True
        self.login.save(update_fields=['is_staff'])
        self.assertFalse(is_teacher_account(self.login))

    def test_signing_in_as_teacher_grants_the_department_and_group(self):
        response = self.client.post(reverse('login'), {
            'username': 'teacher', 'password': 'password',
            'institution_id': self.institution.pk, 'department': 'Teacher',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.session['selected_department'], 'Teacher')
        self.assertTrue(
            InstitutionAccess.objects.filter(
                user=self.login, institution=self.institution, department='Teacher',
            ).exists()
        )
        # The department is mirrored into the permission group on the same login.
        self.assertTrue(self.login.groups.filter(name='Teacher').exists())
        self.assertTrue(self.login.has_perm('students.change_exammark'))
        self.assertFalse(self.login.has_perm('students.add_markcorrectionrequest'))

    def test_a_teacher_can_sign_in_without_an_access_row(self):
        InstitutionAccess.objects.all().delete()
        response = self.client.post(reverse('login'), {
            'username': 'teacher', 'password': 'password',
            'institution_id': self.institution.pk, 'department': 'Teacher',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.session['selected_department'], 'Teacher')

    def test_a_teacher_of_another_institution_cannot_sign_in_here(self):
        self.employee.institution = self.other_institution
        self.employee.save(update_fields=['institution'])
        self.client.post(reverse('login'), {
            'username': 'teacher', 'password': 'password',
            'institution_id': self.institution.pk, 'department': 'Teacher',
        })
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_the_dashboard_sends_a_teacher_to_their_own_classes(self):
        self.sign_in()
        response = self.client.get(reverse('dashboard'))
        self.assertRedirects(response, reverse('teacher_home'), fetch_redirect_response=False)

    def test_an_unlinked_teacher_gets_a_clear_message_not_a_crash(self):
        self.sign_in()
        self.employee.user = None
        self.employee.save(update_fields=['user'])
        response = self.client.get(reverse('teacher_home'))
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('dashboard'), fetch_redirect_response=False)

    def test_sync_removes_the_teacher_group_when_access_is_revoked(self):
        InstitutionAccess.objects.create(
            user=self.login, institution=self.institution, department='Teacher',
        )
        sync_user_department_permissions(self.login)
        self.assertTrue(self.login.groups.filter(name='Teacher').exists())
        InstitutionAccess.objects.filter(user=self.login).update(is_active=False)
        sync_user_department_permissions(self.login)
        self.assertFalse(self.login.groups.filter(name='Teacher').exists())


class TeacherScopeTests(TeacherBase):
    def test_only_the_assigned_class_is_visible(self):
        students = teacher_students(self.employee)
        self.assertEqual(list(students.values_list('pk', flat=True)), [self.my_student.pk])

    def test_a_class_wide_assignment_covers_every_section(self):
        self.assignment.section = ''
        self.assignment.save(update_fields=['section'])
        students = teacher_students(self.employee)
        self.assertEqual(students.count(), 1)
        section_b = Student.objects.create(
            institution=self.institution, student_id='TH004', name='Salma Begum',
            admission_class='9', section='B', roll_no=4, admission_year=2026,
            group='SCI', religion='Islam', guardian_contact_no='01812345681',
        )
        self.assertEqual(teacher_students(self.employee).count(), 2)
        self.assertIn(section_b, teacher_students(self.employee))

    def test_another_sections_student_of_the_same_class_is_out(self):
        Student.objects.create(
            institution=self.institution, student_id='TH005', name='Jamal Hossain',
            admission_class='9', section='B', roll_no=5, admission_year=2026,
            group='SCI', religion='Islam', guardian_contact_no='01812345682',
        )
        self.assertEqual(teacher_students(self.employee).count(), 1)

    def test_subjects_come_from_the_assignments_only(self):
        self.assertEqual(
            list(teacher_subjects(self.employee).values_list('pk', flat=True)),
            [self.math.pk],
        )
        self.assertNotIn(self.english, teacher_subjects(self.employee))

    def test_exams_cover_the_assigned_class_only(self):
        self.assertEqual(
            list(teacher_exams(self.employee).values_list('pk', flat=True)),
            [self.exam.pk],
        )
        self.assertNotIn(self.other_exam, teacher_exams(self.employee))

    def test_nothing_of_another_institution_ever_appears(self):
        self.assertNotIn(self.foreign_student, teacher_students(self.employee))
        self.assertFalse(
            teacher_students(self.employee).filter(institution=self.other_institution).exists()
        )

    def test_an_inactive_assignment_grants_nothing(self):
        self.assignment.is_active = False
        self.assignment.save(update_fields=['is_active'])
        self.assertEqual(teacher_students(self.employee).count(), 0)
        self.assertEqual(teacher_subjects(self.employee).count(), 0)


class TeacherMarkEntryTests(TeacherBase):
    def test_my_classes_lists_only_my_paper(self):
        self.sign_in()
        response = self.client.get(reverse('teacher_home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Mathematics')
        self.assertNotContains(response, 'English')
        self.assertContains(response, reverse('enter_marks', args=[self.exam.pk, self.math.pk]))

    def test_i_can_open_my_own_paper(self):
        self.sign_in()
        response = self.client.get(
            reverse('enter_marks', args=[self.exam.pk, self.math.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Rahim Uddin')
        self.assertNotContains(response, 'Karim Mia')

    def test_i_cannot_open_a_paper_i_do_not_teach(self):
        self.sign_in()
        response = self.client.get(
            reverse('enter_marks', args=[self.exam.pk, self.english.pk])
        )
        self.assertRedirects(response, reverse('teacher_home'), fetch_redirect_response=False)

    def test_i_cannot_open_a_class_i_do_not_teach(self):
        self.sign_in()
        response = self.client.get(
            reverse('enter_marks', args=[self.other_exam.pk, self.math.pk])
        )
        self.assertRedirects(response, reverse('teacher_home'), fetch_redirect_response=False)

    def test_the_subject_picker_offers_only_my_subjects(self):
        self.sign_in()
        response = self.client.get(reverse('select_marks_subject', args=[self.exam.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Mathematics')
        self.assertNotContains(response, 'English')

    def test_the_teacher_group_has_no_approval_path(self):
        InstitutionAccess.objects.create(
            user=self.login, institution=self.institution, department='Teacher',
        )
        sync_user_department_permissions(self.login)
        row = self.file_request()
        row.status = 'SUBMITTED'
        row.save(update_fields=['status'])
        self.sign_in()
        response = self.client.post(
            reverse('approve_mark_correction_request', args=[row.pk])
        )
        # Turned away by the department guard, not silently approved.
        self.assertEqual(response.status_code, 302)
        row.refresh_from_db()
        self.assertEqual(row.status, 'SUBMITTED')
        self.mark.refresh_from_db()
        self.assertEqual(self.mark.cq_obtained, Decimal('40'))


class TeacherCorrectionTests(TeacherBase):
    def test_my_corrections_lists_the_office_filing_about_my_student(self):
        self.file_request()
        self.sign_in()
        response = self.client.get(reverse('teacher_correction_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Rahim Uddin')

    def test_another_classs_application_is_not_listed(self):
        self.file_request(student=self.other_class_student)
        self.sign_in()
        response = self.client.get(reverse('teacher_correction_list'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Karim Mia')

    def test_opening_another_classs_application_is_a_404(self):
        row = self.file_request(student=self.other_class_student)
        self.sign_in()
        response = self.client.get(
            reverse('mark_correction_request_detail', args=[row.pk])
        )
        self.assertEqual(response.status_code, 404)

    def test_i_can_read_print_and_submit_my_own(self):
        row = self.file_request()
        self.sign_in()
        detail = self.client.get(reverse('mark_correction_request_detail', args=[row.pk]))
        self.assertEqual(detail.status_code, 200)
        printed = self.client.get(reverse('mark_correction_request_print', args=[row.pk]))
        self.assertEqual(printed.status_code, 200)
        submit = self.client.post(
            reverse('submit_mark_correction_request', args=[row.pk]),
            {'teacher_note': 'Checked against the answer script'},
        )
        self.assertEqual(submit.status_code, 302)
        row.refresh_from_db()
        self.assertEqual(row.status, 'SUBMITTED')
        self.assertEqual(row.submitted_by, self.login)

    def test_the_detail_page_hides_the_decision_form_from_a_teacher(self):
        row = self.file_request()
        row.status = 'SUBMITTED'
        row.save(update_fields=['status'])
        self.sign_in()
        response = self.client.get(reverse('mark_correction_request_detail', args=[row.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Approve — change the mark')
        self.assertNotContains(response, 'Edit numbers')

    def test_the_detail_page_shows_the_decision_form_to_the_exam_department(self):
        row = self.file_request()
        row.status = 'SUBMITTED'
        row.save(update_fields=['status'])
        self.client.force_login(self.exam_dept)
        session = self.client.session
        session['selected_institution_id'] = self.institution.pk
        session['selected_department'] = 'Exam'
        session.save()
        response = self.client.get(reverse('mark_correction_request_detail', args=[row.pk]))
        self.assertContains(response, 'Approve — change the mark')

    def test_withdrawing_is_not_the_teachers_to_do(self):
        row = self.file_request()
        self.sign_in()
        response = self.client.post(
            reverse('withdraw_mark_correction_request', args=[row.pk])
        )
        self.assertEqual(response.status_code, 302)
        row.refresh_from_db()
        self.assertEqual(row.status, 'DRAFT')

    def test_the_teacher_department_cannot_file_a_new_application(self):
        self.sign_in()
        response = self.client.get(reverse('add_mark_correction_request'))
        self.assertRedirects(
            response, reverse('teacher_correction_list'), fetch_redirect_response=False,
        )
        self.assertEqual(MarkCorrectionRequest.objects.count(), 0)

    def test_the_corrections_register_sends_a_teacher_to_their_own_list(self):
        self.sign_in()
        response = self.client.get(reverse('mark_correction_request_list'))
        self.assertRedirects(
            response, reverse('teacher_correction_list'), fetch_redirect_response=False,
        )
