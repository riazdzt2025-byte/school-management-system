"""OF-07 — Admission & import integrity audit (prompt 15).

Coverage matrix (step × happy / boundary / invalid / unauthorized /
cross-institution). Every test uses synthetic data only.

Admission transitions   office approve/reject/handoff, accounts payment approval
Payment approval        fee mismatch (blocked), capacity (blocked / last seat),
                        atomicity (all-or-nothing), receipt-number collisions
Student Excel import    duplicate roll, blank roll, re-run with '09' vs '9',
                        capacity with '09' vs '9', row-level errors, scoped clerk
Add/Edit student form   duplicate roll on save
Marks Excel import      non-numeric / blank vs 0 / out of range / unknown rows /
                        wrong file format — whole-file reject on any bad value
"""
import io
from datetime import date
from unittest import mock

import openpyxl
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.messages import get_messages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse

from .forms import StudentForm
from .models import (
    AdmissionApplication, AuditLog, Exam, ExamMark, Fee, Institution,
    InstitutionAccess, MoneyReceipt, SectionCapacity, Student, Subject,
    SubjectRequirement, class_label_spellings,
)


XLSX_TYPE = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
STUDENT_HEADERS = [
    'Institution', 'Name', 'Admission Class', 'Section', 'Admission Year',
    'Roll No', 'Gender', 'Religion', "Father's Name", 'Contact No',
    'Guardian Contact No', 'Group',
]
PAYMENT = {
    'payment_amount': '1500.00', 'payment_date': '2026-08-27',
    'payment_purpose': 'Admission Fee', 'account_remarks': 'Paid',
}


def messages_of(response):
    return [str(m.message) for m in get_messages(response.wsgi_request)]


def student_sheet(rows, headers=None):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(headers or STUDENT_HEADERS)
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return SimpleUploadedFile('students.xlsx', buf.read(), content_type=XLSX_TYPE)


def student_row(institution_name, name, admission_class, section, roll, *,
                year=2026, contact='01800000000', group=''):
    # The legacy "Contact No" column is a fallback when the guardian column is
    # blank (old-template support), so a deliberately missing contact must be
    # blank in both columns.
    return [institution_name, name, admission_class, section, year, roll,
            'Male', 'Islam', 'Guardian', contact, contact, group]


def make_application(institution, **overrides):
    values = dict(
        institution=institution, applicant_name='Applicant', guardian_name='Guardian',
        guardian_contact_no='01900000000', requested_class='6', requested_section='A',
        session='2026-2027', status='ACCOUNT_PENDING',
    )
    values.update(overrides)
    return AdmissionApplication.objects.create(**values)


class AdmissionFixtureMixin:
    def setUp(self):
        self.institution = Institution.objects.create(name='OF07 School', classes='6,7,9')
        self.other_institution = Institution.objects.create(name='OF07 Other', classes='6')
        self.admin = get_user_model().objects.create_superuser(
            username='of07-admin', password='password', email='admin@example.com',
        )
        self.client.force_login(self.admin)

    def post_action(self, application, action, data=None):
        return self.client.post(
            reverse(action, args=[application.pk]), data or {},
        )


class OfficeTransitionTests(AdmissionFixtureMixin, TestCase):
    def test_each_transition_writes_one_audit_row(self):
        app = make_application(self.institution, status='SUBMITTED')
        self.post_action(app, 'office_approve_application', {'remarks': 'Verified'})
        self.post_action(app, 'office_handoff_application')
        app.refresh_from_db()
        self.assertEqual(app.status, 'ACCOUNT_PENDING')
        self.assertEqual(app.office_actor, self.admin)
        approve_audit = AuditLog.objects.get(object_id=str(app.pk), action='application_office_approved')
        self.assertEqual(approve_audit.details.get('remarks'), 'Verified')
        actions = list(
            AuditLog.objects.filter(object_id=str(app.pk))
            .order_by('pk').values_list('action', flat=True)
        )
        self.assertEqual(actions, ['application_office_approved', 'application_account_pending'])

    def test_reject_is_terminal_for_every_later_step(self):
        app = make_application(self.institution, status='SUBMITTED')
        self.post_action(app, 'office_reject_application', {'remarks': 'Documents missing'})
        app.refresh_from_db()
        self.assertEqual(app.status, 'REJECTED')
        self.post_action(app, 'office_approve_application')
        self.post_action(app, 'office_handoff_application')
        self.post_action(app, 'accounts_approve_payment', PAYMENT)
        app.refresh_from_db()
        self.assertEqual(app.status, 'REJECTED')
        self.assertFalse(Student.objects.filter(admission_application=app).exists())
        self.assertEqual(
            AuditLog.objects.filter(object_id=str(app.pk), action='application_rejected').count(), 1,
        )

    def test_cannot_reject_an_enrolled_application(self):
        app = make_application(self.institution)
        self.post_action(app, 'accounts_approve_payment', PAYMENT)
        app.refresh_from_db()
        self.assertEqual(app.status, 'ENROLLED')
        self.post_action(app, 'office_reject_application', {'remarks': 'late'})
        app.refresh_from_db()
        self.assertEqual(app.status, 'ENROLLED')
        self.assertIsNotNone(app.enrolled_student_id)

    def test_handoff_before_office_approval_is_refused(self):
        app = make_application(self.institution, status='SUBMITTED')
        self.post_action(app, 'office_handoff_application')
        app.refresh_from_db()
        self.assertEqual(app.status, 'SUBMITTED')
        self.assertFalse(AuditLog.objects.filter(object_id=str(app.pk)).exists())

    def test_office_transition_without_permission_is_refused(self):
        plain = get_user_model().objects.create_user(username='plain', password='password')
        self.client.force_login(plain)
        app = make_application(self.institution, status='SUBMITTED')
        response = self.post_action(app, 'office_approve_application')
        self.assertEqual(response.status_code, 403)
        app.refresh_from_db()
        self.assertEqual(app.status, 'SUBMITTED')

    def test_scoped_office_user_cannot_transition_another_institutions_application(self):
        clerk = get_user_model().objects.create_user(username='clerk', password='password')
        clerk.user_permissions.add(Permission.objects.get(codename='change_admissionapplication'))
        InstitutionAccess.objects.create(
            user=clerk, institution=self.other_institution, department='Office',
        )
        self.client.force_login(clerk)
        session = self.client.session
        session['selected_institution_id'] = str(self.other_institution.pk)
        session['selected_department'] = 'Office'
        session.save()
        app = make_application(self.institution, status='SUBMITTED')
        response = self.post_action(app, 'office_approve_application')
        self.assertEqual(response.status_code, 404)
        app.refresh_from_db()
        self.assertEqual(app.status, 'SUBMITTED')


class PaymentApprovalTests(AdmissionFixtureMixin, TestCase):
    def test_amount_differing_from_fee_schedule_is_blocked(self):
        Fee.objects.create(institution=self.institution, admission_class='6',
                           purpose='Admission Fee', amount=1500)
        app = make_application(self.institution)
        response = self.post_action(app, 'accounts_approve_payment', dict(PAYMENT, payment_amount='1000'))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(any('does not match the fee schedule' in m for m in messages_of(response)))
        app.refresh_from_db()
        self.assertEqual(app.status, 'ACCOUNT_PENDING')
        self.assertIsNone(app.enrolled_student_id)
        self.assertEqual(Student.objects.count(), 0)
        self.assertEqual(MoneyReceipt.objects.count(), 0)

    def test_amount_equal_to_fee_schedule_is_approved(self):
        Fee.objects.create(institution=self.institution, admission_class='6',
                           purpose='Admission Fee', amount=1500)
        app = make_application(self.institution)
        self.post_action(app, 'accounts_approve_payment', dict(PAYMENT, payment_amount='1500'))
        app.refresh_from_db()
        self.assertEqual(app.status, 'ENROLLED')
        self.assertEqual(MoneyReceipt.objects.count(), 1)

    def test_full_section_blocks_approval_with_no_writes(self):
        SectionCapacity.objects.create(institution=self.institution, admission_class='6',
                                       section='A', capacity=1)
        Student.objects.create(institution=self.institution, name='Seated', admission_class='6',
                               section='A', admission_year=2026, status='ACTIVE')
        app = make_application(self.institution)
        response = self.post_action(app, 'accounts_approve_payment', PAYMENT)
        self.assertTrue(any('already at its student limit' in m for m in messages_of(response)))
        app.refresh_from_db()
        self.assertEqual(app.status, 'ACCOUNT_PENDING')
        self.assertEqual(Student.objects.count(), 1)
        self.assertEqual(MoneyReceipt.objects.count(), 0)

    def test_last_seat_goes_to_the_first_approval_only(self):
        SectionCapacity.objects.create(institution=self.institution, admission_class='6',
                                       section='A', capacity=2)
        Student.objects.create(institution=self.institution, name='Seated', admission_class='6',
                               section='A', admission_year=2026, status='ACTIVE')
        first = make_application(self.institution, applicant_name='First')
        second = make_application(self.institution, applicant_name='Second')
        self.post_action(first, 'accounts_approve_payment', PAYMENT)
        self.post_action(second, 'accounts_approve_payment', PAYMENT)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.status, 'ENROLLED')
        self.assertEqual(second.status, 'ACCOUNT_PENDING')
        self.assertEqual(
            Student.objects.filter(section='A', admission_class='6', status='ACTIVE').count(), 2,
        )

    def test_failure_after_student_creation_rolls_everything_back(self):
        app = make_application(self.institution)
        with mock.patch('students.views.record_audit', side_effect=RuntimeError('audit down')):
            with self.assertRaises(RuntimeError):
                self.post_action(app, 'accounts_approve_payment', PAYMENT)
        app.refresh_from_db()
        self.assertEqual(app.status, 'ACCOUNT_PENDING')
        self.assertIsNone(app.enrolled_student_id)
        self.assertEqual(Student.objects.count(), 0)
        self.assertEqual(MoneyReceipt.objects.count(), 0)

    def test_receipt_number_collision_is_retried_with_a_new_number(self):
        existing_student = Student.objects.create(
            institution=self.institution, name='Old', admission_class='6', admission_year=2026,
        )
        taken = f'ADM-{date.today():%Y}-AAAAAAAAAA'
        MoneyReceipt.objects.create(student=existing_student, receipt_no=taken,
                                    purpose='x', amount=1, date=date.today())
        app = make_application(self.institution)
        fresh = mock.Mock(hex='bbbbbbbbbb' + '0' * 22)
        with mock.patch('students.views.uuid4', side_effect=[mock.Mock(hex='aaaaaaaaaa' + '0' * 22), fresh]):
            self.post_action(app, 'accounts_approve_payment', PAYMENT)
        app.refresh_from_db()
        self.assertEqual(app.status, 'ENROLLED')
        self.assertEqual(MoneyReceipt.objects.get(student=app.enrolled_student).receipt_no,
                         f'ADM-{date.today():%Y}-BBBBBBBBBB')

    def test_exhausted_receipt_numbers_roll_back_the_whole_approval(self):
        existing_student = Student.objects.create(
            institution=self.institution, name='Old', admission_class='6', admission_year=2026,
        )
        taken = f'ADM-{date.today():%Y}-AAAAAAAAAA'
        MoneyReceipt.objects.create(student=existing_student, receipt_no=taken,
                                    purpose='x', amount=1, date=date.today())
        app = make_application(self.institution)
        same = mock.Mock(hex='aaaaaaaaaa' + '0' * 22)
        with mock.patch('students.views.uuid4', return_value=same):
            with self.assertRaises(IntegrityError):
                self.post_action(app, 'accounts_approve_payment', PAYMENT)
        app.refresh_from_db()
        self.assertEqual(app.status, 'ACCOUNT_PENDING')
        self.assertEqual(Student.objects.count(), 1)  # only the pre-existing one
        self.assertEqual(MoneyReceipt.objects.count(), 1)

    def test_payment_on_rejected_application_creates_nothing(self):
        app = make_application(self.institution, status='REJECTED')
        response = self.post_action(app, 'accounts_approve_payment', PAYMENT)
        self.assertTrue(any('not valid for this application' in m for m in messages_of(response)))
        self.assertEqual(Student.objects.count(), 0)


class StudentImportIntegrityTests(AdmissionFixtureMixin, TestCase):
    def upload(self, rows):
        return self.client.post(reverse('import_students'), {'excel_file': student_sheet(rows)})

    def seat(self, **overrides):
        values = dict(institution=self.institution, name='Existing', admission_class='6',
                      section='A', admission_year=2026, roll_no=5, status='ACTIVE')
        values.update(overrides)
        return Student.objects.create(**values)

    def test_duplicate_roll_in_same_section_is_rejected_and_reported(self):
        self.seat(roll_no=5)
        response = self.upload([student_row(self.institution.name, 'Newcomer', '6', 'A', 5)])
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Student.objects.filter(name='Newcomer').exists())
        self.assertTrue(any('roll no 5 is already used' in m for m in messages_of(response)))

    def test_blank_rolls_are_not_treated_as_duplicates(self):
        response = self.upload([
            student_row(self.institution.name, 'No Roll One', '6', 'A', ''),
            student_row(self.institution.name, 'No Roll Two', '6', 'A', ''),
        ])
        self.assertEqual(Student.objects.filter(name__startswith='No Roll').count(), 2)
        self.assertFalse(any('already used' in m for m in messages_of(response)))

    def test_same_roll_in_another_section_is_allowed(self):
        self.seat(roll_no=5, section='A')
        self.upload([student_row(self.institution.name, 'Section B Kid', '6', 'B', 5)])
        self.assertTrue(Student.objects.filter(name='Section B Kid', section='B').exists())

    def test_roll_held_by_a_transferred_student_is_free(self):
        self.seat(roll_no=5, status='TRANSFERRED')
        self.upload([student_row(self.institution.name, 'Takes Over', '6', 'A', 5)])
        self.assertTrue(Student.objects.filter(name='Takes Over', roll_no=5).exists())

    def test_rerun_with_zero_padded_class_is_not_created_twice(self):
        # Stored as '9'; the sheet now says '09' for the same student.
        self.seat(name='Rerun Kid', admission_class='9', section='A', roll_no=3, admission_year=2026)
        before = Student.objects.count()
        response = self.upload([student_row(self.institution.name, 'Rerun Kid', '09', 'A', 3)])
        self.assertEqual(Student.objects.count(), before)
        self.assertTrue(any('already present' in m for m in messages_of(response)))

    def test_capacity_counts_students_stored_with_a_padded_class(self):
        # Limit set on '9'; the seated student was stored as '09' — still full.
        SectionCapacity.objects.create(institution=self.institution, admission_class='9',
                                       section='A', capacity=1)
        self.seat(admission_class='09', section='A', roll_no=1)
        response = self.upload([student_row(self.institution.name, 'Over Limit', '9', 'A', 2)])
        self.assertFalse(Student.objects.filter(name='Over Limit').exists())
        self.assertTrue(any('is full' in m for m in messages_of(response)))

    def test_capacity_limit_stored_padded_applies_to_unpadded_class(self):
        SectionCapacity.objects.create(institution=self.institution, admission_class='09',
                                       section='A', capacity=1)
        self.seat(admission_class='9', section='A', roll_no=1)
        self.assertFalse(SectionCapacity.has_room(self.institution, '9', 'A'))
        self.assertFalse(SectionCapacity.has_room(self.institution, '09', 'A'))

    def test_bad_rows_are_reported_by_row_and_good_rows_still_import(self):
        response = self.upload([
            student_row(self.institution.name, 'Good One', '6', 'A', 1),
            student_row(self.institution.name, 'No Guardian', '6', 'A', 2, contact=''),
            student_row(self.institution.name, 'Bad Contact', '6', 'A', 3, contact='12345'),
            student_row(self.institution.name, '', '6', 'A', 4),
            student_row(self.institution.name, 'Bad Year', '6', 'A', 5, year='abc'),
            student_row(self.institution.name, 'Good Two', '6', 'A', 6),
        ])
        self.assertEqual(
            sorted(Student.objects.values_list('name', flat=True)), ['Good One', 'Good Two'],
        )
        text = ' | '.join(messages_of(response))
        self.assertIn('Row 3: guardian contact number is missing', text)
        self.assertIn('Row 4: invalid guardian contact number', text)
        self.assertIn('Row 5: name or class is empty', text)
        self.assertIn('Row 6: ValueError', text)
        self.assertIn('4 row(s) had issues', text)
        success = [m for m in messages_of(response) if 'student(s) added' in m]
        self.assertEqual(len(success), 1)
        self.assertTrue(success[0].startswith('2 student(s) added'))

    def test_row_for_an_unknown_institution_is_refused(self):
        response = self.upload([student_row('No Such School', 'Lost', '6', 'A', 1)])
        self.assertFalse(Student.objects.filter(name='Lost').exists())
        self.assertTrue(any("institution 'No Such School' not found" in m for m in messages_of(response)))

    def test_imported_students_get_distinct_generated_ids(self):
        self.upload([
            student_row(self.institution.name, 'Twin A', '6', 'A', 1),
            student_row(self.institution.name, 'Twin B', '6', 'A', 2),
        ])
        ids = list(Student.objects.filter(name__startswith='Twin').values_list('student_id', flat=True))
        self.assertEqual(len(ids), 2)
        self.assertEqual(len(set(ids)), 2)
        self.assertTrue(all(i.startswith('2026' + '06') for i in ids))


class StudentFormRollTests(TestCase):
    def setUp(self):
        self.institution = Institution.objects.create(name='Form School', classes='6')
        self.user = get_user_model().objects.create_superuser(
            username='form-admin', password='password', email='f@example.com',
        )
        self.seated = Student.objects.create(
            institution=self.institution, name='Seated', admission_class='6',
            section='A', admission_year=2026, roll_no=7,
        )

    def data(self, **overrides):
        values = {
            'institution': self.institution.pk, 'name': 'New Student',
            'admission_class': '6', 'section': 'A', 'admission_year': 2026,
            'status': 'ACTIVE',
            'roll_no': 7, 'gender': 'M', 'religion': 'Islam',
            'guardian_contact_no': '01800000000', 'group': '',
        }
        values.update(overrides)
        return values

    def test_new_student_with_a_taken_roll_is_rejected(self):
        form = StudentForm(data=self.data(), user=self.user)
        self.assertFalse(form.is_valid())
        self.assertIn('roll_no', form.errors)

    def test_new_student_with_a_free_roll_is_accepted(self):
        form = StudentForm(data=self.data(roll_no=8), user=self.user)
        self.assertTrue(form.is_valid(), form.errors)

    def test_editing_a_student_keeps_their_own_roll(self):
        form = StudentForm(data=self.data(name='Seated Renamed'), user=self.user, instance=self.seated)
        self.assertTrue(form.is_valid(), form.errors)

    def test_moving_into_a_taken_roll_is_rejected(self):
        other = Student.objects.create(
            institution=self.institution, name='Other', admission_class='6',
            section='A', admission_year=2026, roll_no=9,
        )
        form = StudentForm(data=self.data(roll_no=7), user=self.user, instance=other)
        self.assertFalse(form.is_valid())
        self.assertIn('roll_no', form.errors)


class ClassLabelHelperTests(TestCase):
    def test_zero_padded_spellings_are_one_class(self):
        self.assertEqual(class_label_spellings('9'), ['09', '9'])
        self.assertEqual(class_label_spellings('09'), ['09', '9'])
        self.assertEqual(class_label_spellings(' 10 '), ['10'])
        self.assertEqual(class_label_spellings('Nursery'), ['Nursery'])
        self.assertEqual(class_label_spellings(''), [])


class MarksImportIntegrityTests(TestCase):
    """Subject marks import with a total-only (no parts) subject: Roll, ID, Name, Marks."""

    def setUp(self):
        self.institution = Institution.objects.create(name='Marks Audit School', classes='9')
        self.user = get_user_model().objects.create_superuser(
            username='marks-audit', password='password', email='m@example.com',
        )
        self.client.force_login(self.user)
        self.physics = Subject.objects.create(code='PHY', name='Physics', full_marks=100)
        SubjectRequirement.objects.create(
            institution=self.institution, admission_class='9', group='SCI',
            subject=self.physics, requirement_type='MANDATORY',
        )
        self.exam = Exam.objects.create(
            name='Audit Term-2026', exam_type='SECOND_TERM', institution=self.institution,
            admission_class='9', section='', group='SCI', session='2026',
        )
        self.alpha = self.make_student('A001', 'Alpha', 1)
        self.beta = self.make_student('A002', 'Beta', 2)

    def make_student(self, student_id, name, roll):
        return Student.objects.create(
            institution=self.institution, student_id=student_id, name=name,
            admission_class='9', section='A', group='SCI', roll_no=roll, admission_year=2026,
        )

    def upload(self, rows, headers=('Roll', 'ID', 'Name', 'Marks')):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = '9SC Physics'
        ws.append(list(headers))
        for row in rows:
            ws.append(row)
        buf = io.BytesIO()
        wb.save(buf)
        upload = SimpleUploadedFile('9SC Physics.xlsx', buf.getvalue(), content_type=XLSX_TYPE)
        return self.client.post(
            reverse('import_exam_marks', args=[self.exam.pk]),
            {'subject': str(self.physics.pk), 'excel_file': upload},
        )

    def mark_of(self, student):
        return ExamMark.objects.filter(exam=self.exam, student=student, subject=self.physics).first()

    def test_non_numeric_mark_rejects_the_whole_file(self):
        response = self.upload([[1, 'A001', 'Alpha', 'abc'], [2, 'A002', 'Beta', 40]])
        self.assertTrue(any('Import rejected' in m for m in messages_of(response)))
        self.assertEqual(ExamMark.objects.count(), 0)  # Beta's valid mark is not silently saved

    def test_blank_mark_is_skipped_and_zero_is_saved(self):
        response = self.upload([[1, 'A001', 'Alpha', None], [2, 'A002', 'Beta', 0]])
        self.assertIsNone(self.mark_of(self.alpha))
        self.assertEqual(str(self.mark_of(self.beta).marks_obtained), '0.00')
        self.assertTrue(any('1 row(s) skipped' in m for m in messages_of(response)))

    def test_mark_above_full_marks_or_negative_rejects_the_file(self):
        self.upload([[1, 'A001', 'Alpha', 101]])
        self.assertEqual(ExamMark.objects.count(), 0)
        self.upload([[1, 'A001', 'Alpha', -5]])
        self.assertEqual(ExamMark.objects.count(), 0)

    def test_unknown_student_rows_are_skipped_and_counted(self):
        response = self.upload([[1, 'A001', 'Alpha', 55], [99, 'NOPE', 'Ghost', 70]])
        self.assertEqual(str(self.mark_of(self.alpha).marks_obtained), '55.00')
        self.assertEqual(ExamMark.objects.count(), 1)
        self.assertTrue(any('1 row(s) skipped' in m for m in messages_of(response)))

    def test_file_without_roll_or_id_columns_is_rejected(self):
        response = self.upload([['Alpha', 55]], headers=('Name', 'Score'))
        self.assertTrue(any('Import rejected' in m or 'Could not import' in m for m in messages_of(response)))
        self.assertEqual(ExamMark.objects.count(), 0)
