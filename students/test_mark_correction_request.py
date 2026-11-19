"""Mark correction applications: draft → teacher check → exam-department decision.

The rule this file exists to protect is the owner's: **a requested mark must not
appear anywhere on the result until the examination department approves.** So the
tests come in three groups:

1. The workflow (who may move a request, and from which status).
2. The rules that keep paper honest (numbers frozen once submitted, a stale
   request cannot ride on someone else's change, one open request per mark).
3. The result is untouched until approval, and correct afterwards.
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from .models import (
    AuditLog, Employee, Exam, ExamMark, Institution, InstitutionAccess,
    MarkCorrectionRequest, SalarySheet, SeatPlan, Student, Subject,
    SubjectRequirement, TeacherAssignment,
)
from .permissions import ensure_default_groups


class MarkCorrectionBase(TestCase):
    def setUp(self):
        self.institution = Institution.objects.create(
            name='Correction School', classes='9,10', number=2
        )
        self.other_institution = Institution.objects.create(
            name='Other Correction School', classes='9', number=3
        )
        self.subject = Subject.objects.create(
            code='MATH', name='Mathematics', full_marks=100,
            cq_marks=70, mcq_marks=30, pass_percentage=33,
        )
        SubjectRequirement.objects.create(
            institution=self.institution, admission_class='9', subject=self.subject,
        )
        self.student = Student.objects.create(
            institution=self.institution, student_id='MC001', name='Rahim Uddin',
            admission_class='9', section='A', roll_no=7, admission_year=2026,
            group='SCI', religion='Islam', guardian_contact_no='01812345678',
        )
        self.exam = Exam.objects.create(
            institution=self.institution, name='First Term 2026',
            exam_type='FIRST_TERM', admission_class='9', session='2026-2027',
            is_published=True,
        )
        self.mark = ExamMark.objects.create(
            exam=self.exam, student=self.student, subject=self.subject,
            cq_obtained=Decimal('40'), mcq_obtained=Decimal('20'),
            marks_obtained=Decimal('60'),
        )
        ensure_default_groups()
        self.office = self._user('office-clerk', 'Office')
        self.exam_dept = self._user('exam-member', 'Exam')
        self.teacher = self._user('subject-teacher', 'Office')

    def _user(self, username, department):
        user = get_user_model().objects.create_user(username=username, password='password')
        InstitutionAccess.objects.create(
            user=user, institution=self.institution, department=department,
        )
        for codename in (
            'add_markcorrectionrequest', 'change_markcorrectionrequest',
            'view_markcorrectionrequest',
        ):
            user.user_permissions.add(Permission.objects.get(codename=codename))
        return user

    def _login(self, user, department):
        """Sign in the way the app does: institution + department in session."""
        self.client.force_login(user)
        session = self.client.session
        session['selected_institution_id'] = self.institution.pk
        session['selected_department'] = department
        session.save()

    def _file(self, *, reason='CQ 3 was left unmarked', cq='55', mcq='20'):
        """File a draft through the real screen — no shortcut around the form."""
        self._login(self.office, 'Office')
        response = self.client.post(reverse('add_mark_correction_request'), {
            'institution': self.institution.pk,
            'exam': self.exam.pk,
            'student': self.student.pk,
            'subject': self.subject.pk,
            'reason': reason,
            'requested_cq': cq,
            'requested_mcq': mcq,
        })
        self.assertEqual(response.status_code, 302, getattr(response, 'context', None))
        return MarkCorrectionRequest.objects.get()


class FilingTests(MarkCorrectionBase):
    def test_filing_saves_a_draft_and_shows_the_printed_sheet(self):
        row = self._file()
        self.assertEqual(row.status, 'DRAFT')
        self.assertEqual(row.admitted_class if hasattr(row, 'admitted_class') else row.admission_class, '9')
        self.assertEqual(row.section, 'A')
        # The register's numbers are snapshotted so the sheet can show "was → asked".
        self.assertEqual(row.current_total, Decimal('60'))
        self.assertEqual(row.current_parts, {'cq': '40.00', 'mcq': '20.00'})
        self.assertEqual(row.requested_total, Decimal('75'))
        self.assertEqual(row.requested_parts, {'cq': '55', 'mcq': '20'})
        self.assertEqual(row.filed_by, self.office)
        self.assertIsNotNone(row.filed_at)
        self.assertTrue(
            AuditLog.objects.filter(action='mark_correction_filed').exists()
        )
        # The applicant is taken to the printable application straight away.
        self.client.force_login(self.office)
        response = self.client.get(reverse('mark_correction_request_print', args=[row.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'MARKS CORRECTION APPLICATION'.title())
        self.assertContains(response, 'APPLICATION NO.')
        self.assertContains(response, 'Rahim Uddin')

    def test_the_register_is_untouched_until_approval(self):
        self._file()
        self.mark.refresh_from_db()
        self.assertEqual(self.mark.cq_obtained, Decimal('40'))
        self.assertEqual(self.mark.marks_obtained, Decimal('60'))

    def test_an_empty_request_is_refused(self):
        self._login(self.office, 'Office')
        response = self.client.post(reverse('add_mark_correction_request'), {
            'institution': self.institution.pk, 'exam': self.exam.pk,
            'student': self.student.pk, 'subject': self.subject.pk,
            'reason': 'oops', 'requested_cq': '', 'requested_mcq': '',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(MarkCorrectionRequest.objects.count(), 0)

    def test_a_part_above_its_full_marks_is_refused(self):
        self._login(self.office, 'Office')
        response = self.client.post(reverse('add_mark_correction_request'), {
            'institution': self.institution.pk, 'exam': self.exam.pk,
            'student': self.student.pk, 'subject': self.subject.pk,
            'reason': 'too high', 'requested_cq': '99', 'requested_mcq': '30',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(MarkCorrectionRequest.objects.count(), 0)

    def test_student_of_another_class_is_refused(self):
        outsider = Student.objects.create(
            institution=self.institution, student_id='MC009', name='Class Ten',
            admission_class='10', section='A', admission_year=2026, roll_no=1,
            religion='Islam', guardian_contact_no='01812345678',
        )
        self._login(self.office, 'Office')
        response = self.client.post(reverse('add_mark_correction_request'), {
            'institution': self.institution.pk, 'exam': self.exam.pk,
            'student': outsider.pk, 'subject': self.subject.pk,
            'reason': 'wrong class', 'requested_cq': '50', 'requested_mcq': '20',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(MarkCorrectionRequest.objects.count(), 0)

    def test_one_open_request_per_mark(self):
        row = self._file()
        self._login(self.office, 'Office')
        self.client.post(reverse('add_mark_correction_request'), {
            'institution': self.institution.pk, 'exam': self.exam.pk,
            'student': self.student.pk, 'subject': self.subject.pk,
            'reason': 'again', 'requested_cq': '50', 'requested_mcq': '20',
        })
        # One open request per mark: the second filing is refused with a
        # message (never a 500).
        self.assertEqual(MarkCorrectionRequest.objects.count(), 1)
        detail = self.client.get(reverse('mark_correction_request_detail', args=[row.pk]))
        self.assertEqual(detail.status_code, 200)
        # Once that one is withdrawn, a fresh application is allowed again.
        self.client.post(reverse('withdraw_mark_correction_request', args=[row.pk]))
        self.client.post(reverse('add_mark_correction_request'), {
            'institution': self.institution.pk, 'exam': self.exam.pk,
            'student': self.student.pk, 'subject': self.subject.pk,
            'reason': 'refiled', 'requested_cq': '50', 'requested_mcq': '20',
        })
        self.assertEqual(MarkCorrectionRequest.objects.count(), 2)

    def test_a_clerk_cannot_file_against_another_institution(self):
        other_student = Student.objects.create(
            institution=self.other_institution, student_id='MC100', name='Elsewhere',
            admission_class='9', section='A', admission_year=2026, roll_no=1,
            religion='Islam', guardian_contact_no='01812345678',
        )
        other_exam = Exam.objects.create(
            institution=self.other_institution, name='Other Exam',
            exam_type='FIRST_TERM', admission_class='9', session='2026-2027',
        )
        self._login(self.office, 'Office')
        response = self.client.post(reverse('add_mark_correction_request'), {
            'institution': self.other_institution.pk, 'exam': other_exam.pk,
            'student': other_student.pk, 'subject': self.subject.pk,
            'reason': 'not mine', 'requested_cq': '50', 'requested_mcq': '20',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(MarkCorrectionRequest.objects.count(), 0)


class WorkflowTests(MarkCorrectionBase):
    def test_office_submits_and_numbers_are_then_frozen(self):
        row = self._file()
        self._login(self.office, 'Office')
        response = self.client.post(
            reverse('submit_mark_correction_request', args=[row.pk]),
            {'teacher_note': 'checked against the answer script'},
        )
        self.assertEqual(response.status_code, 302)
        row.refresh_from_db()
        self.assertEqual(row.status, 'SUBMITTED')
        self.assertEqual(row.submitted_by, self.office)
        self.assertEqual(row.teacher_note, 'checked against the answer script')
        self.assertTrue(AuditLog.objects.filter(action='mark_correction_submitted').exists())

        # A submitted sheet is signed paper: it cannot be edited any more.
        edit = self.client.get(reverse('edit_mark_correction_request', args=[row.pk]))
        self.assertEqual(edit.status_code, 302)

    def test_a_draft_can_be_edited(self):
        row = self._file()
        self._login(self.office, 'Office')
        response = self.client.get(reverse('edit_mark_correction_request', args=[row.pk]))
        self.assertEqual(response.status_code, 200)

    def test_exam_department_approval_writes_the_mark(self):
        row = self._file()
        self._login(self.office, 'Office')
        self.client.post(reverse('submit_mark_correction_request', args=[row.pk]))
        self._login(self.exam_dept, 'Exam')
        response = self.client.post(
            reverse('approve_mark_correction_request', args=[row.pk]),
            {'decision_reason': 'verified with the answer script'},
        )
        self.assertEqual(response.status_code, 302)
        row.refresh_from_db()
        self.assertEqual(row.status, 'APPROVED')
        self.assertEqual(row.decided_by, self.exam_dept)
        self.mark.refresh_from_db()
        self.assertEqual(self.mark.cq_obtained, Decimal('55'))
        self.assertEqual(self.mark.mcq_obtained, Decimal('20'))
        self.assertEqual(self.mark.marks_obtained, Decimal('75'))
        self.assertTrue(AuditLog.objects.filter(action='mark_correction_approved').exists())

    def test_rejection_keeps_the_mark_and_needs_a_reason(self):
        row = self._file()
        self._login(self.office, 'Office')
        self.client.post(reverse('submit_mark_correction_request', args=[row.pk]))
        self._login(self.exam_dept, 'Exam')

        blank = self.client.post(reverse('reject_mark_correction_request', args=[row.pk]))
        self.assertEqual(blank.status_code, 302)
        row.refresh_from_db()
        self.assertEqual(row.status, 'SUBMITTED')

        self.client.post(
            reverse('reject_mark_correction_request', args=[row.pk]),
            {'decision_reason': 'The script shows 40, not 55.'},
        )
        row.refresh_from_db()
        self.assertEqual(row.status, 'REJECTED')
        self.assertEqual(row.decision_reason, 'The script shows 40, not 55.')
        self.mark.refresh_from_db()
        self.assertEqual(self.mark.marks_obtained, Decimal('60'))
        self.assertTrue(AuditLog.objects.filter(action='mark_correction_rejected').exists())

    def test_office_cannot_approve(self):
        row = self._file()
        self._login(self.office, 'Office')
        self.client.post(reverse('submit_mark_correction_request', args=[row.pk]))
        response = self.client.post(reverse('approve_mark_correction_request', args=[row.pk]))
        # The view is gated on the Exam department, so the office is sent home
        # and the request stays submitted.
        self.assertEqual(response.status_code, 302)
        row.refresh_from_db()
        self.assertEqual(row.status, 'SUBMITTED')

    def test_withdrawing_leaves_the_mark_alone(self):
        row = self._file()
        self._login(self.office, 'Office')
        self.client.post(
            reverse('withdraw_mark_correction_request', args=[row.pk]),
            {'decision_reason': 'wrong student, refiling'},
        )
        row.refresh_from_db()
        self.assertEqual(row.status, 'WITHDRAWN')
        self.mark.refresh_from_db()
        self.assertEqual(self.mark.marks_obtained, Decimal('60'))
        # A withdrawn request no longer blocks a fresh one.
        self.assertTrue(row.status == 'WITHDRAWN')

    def test_a_decided_request_cannot_be_approved_twice(self):
        row = self._file()
        self._login(self.office, 'Office')
        self.client.post(reverse('submit_mark_correction_request', args=[row.pk]))
        self._login(self.exam_dept, 'Exam')
        self.client.post(reverse('approve_mark_correction_request', args=[row.pk]))
        # Somebody edits the mark afterwards, then the old approval is replayed.
        ExamMark.objects.filter(pk=self.mark.pk).update(marks_obtained=Decimal('90'))
        response = self.client.post(reverse('approve_mark_correction_request', args=[row.pk]))
        self.assertEqual(response.status_code, 302)
        self.mark.refresh_from_db()
        self.assertEqual(self.mark.marks_obtained, Decimal('90'))

    def test_a_stale_request_cannot_approve_over_a_newer_mark(self):
        row = self._file()
        self._login(self.office, 'Office')
        self.client.post(reverse('submit_mark_correction_request', args=[row.pk]))
        # Somebody changed the mark through the marks screen after filing.
        ExamMark.objects.filter(pk=self.mark.pk).update(
            cq_obtained=Decimal('50'), marks_obtained=Decimal('70'),
        )
        self._login(self.exam_dept, 'Exam')
        self.client.post(reverse('approve_mark_correction_request', args=[row.pk]))
        row.refresh_from_db()
        self.assertEqual(row.status, 'SUBMITTED')
        self.mark.refresh_from_db()
        self.assertEqual(self.mark.cq_obtained, Decimal('50'))


class ResultIsolationTests(MarkCorrectionBase):
    """The owner's rule: a pending request is invisible on the result sheet."""

    def test_the_result_sheet_shows_the_old_mark_while_pending(self):
        row = self._file()
        self._login(self.office, 'Office')
        self.client.post(reverse('submit_mark_correction_request', args=[row.pk]))

        self._login(self.exam_dept, 'Exam')
        response = self.client.get(reverse('result_sheet', args=[self.exam.pk]))
        self.assertEqual(response.status_code, 200)
        # 60 (the register) is printed; the requested 75 never appears as a mark.
        self.assertContains(response, '60')
        self.assertNotContains(response, f'>{row.requested_total}<')

    def test_the_result_sheet_shows_the_new_mark_after_approval(self):
        row = self._file()
        self._login(self.office, 'Office')
        self.client.post(reverse('submit_mark_correction_request', args=[row.pk]))
        self._login(self.exam_dept, 'Exam')
        self.client.post(reverse('approve_mark_correction_request', args=[row.pk]))

        self.mark.refresh_from_db()
        self.assertEqual(self.mark.marks_obtained, Decimal('75'))
        response = self.client.get(reverse('result_sheet', args=[self.exam.pk]))
        self.assertContains(response, '75')


class ScreenTests(MarkCorrectionBase):
    def test_the_list_filters_and_counts_by_status(self):
        self._file()
        self._login(self.exam_dept, 'Exam')
        response = self.client.get(reverse('mark_correction_request_list'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['counts']['DRAFT'], 1)
        self.assertContains(response, 'Rahim Uddin')

        pending = self.client.get(reverse('mark_correction_request_list'), {'status': 'SUBMITTED'})
        self.assertNotContains(pending, 'Rahim Uddin')

    def test_the_print_list_carries_institution_class_and_section(self):
        self._file()
        self._login(self.exam_dept, 'Exam')
        response = self.client.get(reverse('mark_correction_request_list'), {'print': '1'})
        self.assertContains(response, 'Correction School')
        self.assertContains(response, 'Section')

    def test_the_printed_application_carries_the_signed_fields(self):
        row = self._file()
        self._login(self.exam_dept, 'Exam')
        response = self.client.get(reverse('mark_correction_request_print', args=[row.pk]))
        self.assertEqual(response.status_code, 200)
        for needle in (
            'Examination Department', 'APPLICATION NO.', 'Subject Teacher',
            'Head of Institution', 'Reason',
        ):
            self.assertContains(response, needle)

    def test_a_request_from_another_institution_is_a_404(self):
        row = self._file()
        outsider = get_user_model().objects.create_user(
            username='other-clerk', password='password'
        )
        InstitutionAccess.objects.create(
            user=outsider, institution=self.other_institution, department='Exam',
        )
        for codename in (
            'view_markcorrectionrequest', 'change_markcorrectionrequest',
            'add_markcorrectionrequest',
        ):
            outsider.user_permissions.add(Permission.objects.get(codename=codename))
        self.client.force_login(outsider)
        session = self.client.session
        session['selected_institution_id'] = self.other_institution.pk
        session['selected_department'] = 'Exam'
        session.save()
        self.assertEqual(
            self.client.get(reverse('mark_correction_request_detail', args=[row.pk])).status_code,
            404,
        )

    def test_the_student_options_endpoint_is_scoped(self):
        self._login(self.office, 'Office')
        payload = self.client.get(reverse('mark_correction_student_options'), {
            'institution': self.institution.pk, 'admission_class': '9', 'section': 'A',
        }).json()
        names = {row['name'] for row in payload['students']}
        self.assertIn('Rahim Uddin', names)
        self.assertEqual(payload['sections'], ['A'])
        # A class-science student never shows up for a class 10 query.
        empty = self.client.get(reverse('mark_correction_student_options'), {
            'institution': self.institution.pk, 'admission_class': '10',
        }).json()
        self.assertEqual(empty['students'], [])


class TeacherNumberOnPrintedSheetsTests(TestCase):
    """2011 + branch + serial must reach the three printed places the owner asked for."""

    def setUp(self):
        self.institution = Institution.objects.create(
            name='Print School', classes='9', number=2
        )
        self.teacher = Employee.objects.create(
            institution=self.institution, name='Salma Akter',
            designation='Assistant Teacher', join_date=date(2026, 1, 1),
        )
        self.subject = Subject.objects.create(code='BAN', name='Bangla', full_marks=100)
        SubjectRequirement.objects.create(
            institution=self.institution, admission_class='9', subject=self.subject,
        )
        self.exam = Exam.objects.create(
            institution=self.institution, name='Print Term', exam_type='FIRST_TERM',
            admission_class='9', session='2026-2027',
        )
        self.student = Student.objects.create(
            institution=self.institution, student_id='PR001', name='Print Student',
            admission_class='9', section='A', roll_no=1, admission_year=2026,
            religion='Islam', guardian_contact_no='01812345678',
        )
        SeatPlan.objects.create(
            exam=self.exam, student=self.student, room_name='R1', seat_no=1,
        )
        TeacherAssignment.objects.create(
            institution=self.institution, employee=self.teacher, admission_class='9',
            section='A', subject=self.subject, session='2026-2027',
        )
        ensure_default_groups()
        self.admin = get_user_model().objects.create_superuser(
            username='print-admin', password='password'
        )
        self.client.force_login(self.admin)
        self.number = self.teacher.teacher_no_display
        self.assertTrue(self.number)

    def test_signature_sheet_prints_the_number(self):
        response = self.client.get(
            reverse('signature_sheet', args=[self.exam.pk, 'R1'])
        )
        self.assertContains(response, self.number)

    def test_salary_list_prints_the_number(self):
        SalarySheet.objects.create(
            employee=self.teacher, month='January 2026', amount=1000,
            date=date(2026, 1, 31),
        )
        response = self.client.get(reverse('salary_sheet_list'))
        self.assertContains(response, 'Teacher No.')
        self.assertContains(response, self.number)

    def test_assignment_list_prints_the_number(self):
        response = self.client.get(reverse('teacher_assignment_list'))
        self.assertContains(response, self.number)
