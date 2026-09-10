"""Tests for the single canonical guardian contact number.

One primary contact per student / admission application:
"Guardian Contact Number / অভিভাবকের যোগাযোগ নম্বর" (Student.guardian_contact_no
and AdmissionApplication.guardian_contact_no — required on both).

Covers:
* normalisation — leading zero kept, Bangla digits, numeric Excel cells;
* validation — blank/invalid numbers, supported formats;
* the forms and pages carrying exactly one (required) contact input;
* the Excel import (new single-column template + legacy two-column
  template) and the exports;
* the enrolment hand-off (application -> student);
* migration 0040 — backfill of blank guardian numbers, AuditLog archive of
  differing legacy numbers, and the column drop — tested end to end
  against the real migration chain;
* the conflict report's behaviour once the legacy columns are gone.
"""
from datetime import date
from io import BytesIO, StringIO

from django.contrib.auth import get_user_model
from django.core.exceptions import FieldDoesNotExist, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from .forms import AdmissionApplicationForm, StudentForm
from .models import (
    AdmissionApplication, AuditLog, Institution, Student,
    normalize_guardian_contact, validate_guardian_contact,
)

try:
    from openpyxl import Workbook, load_workbook
except ModuleNotFoundError:
    Workbook = None

# The shared test institution every DB-touching class below uses.
INSTITUTION_CLASSES = '6,9'


class GuardianContactNormalizationTests(TestCase):
    """normalize_guardian_contact / validate_guardian_contact unit tests."""

    def test_blank_and_none_become_empty_string(self):
        self.assertEqual(normalize_guardian_contact(None), '')
        self.assertEqual(normalize_guardian_contact(''), '')
        self.assertEqual(normalize_guardian_contact('   '), '')

    def test_leading_zero_is_kept_for_typed_text(self):
        # Stored as a string, never a number: the leading 0 must survive.
        self.assertEqual(normalize_guardian_contact('01812345678'), '01812345678')
        self.assertEqual(normalize_guardian_contact('  01812345678 \n'), '01812345678')

    def test_bangla_digits_are_converted_to_ascii(self):
        self.assertEqual(normalize_guardian_contact('০১৮১২৩৪৫৬৭৮'), '01812345678')

    def test_numeric_excel_cell_gets_its_leading_zero_back(self):
        # Excel drops the leading zero of 01812345678 in a numeric cell and
        # hands the importer the number 1812345678 — a 10-digit number
        # starting with 1 is a Bangladeshi mobile that lost its zero.
        self.assertEqual(normalize_guardian_contact(1812345678), '01812345678')
        self.assertEqual(normalize_guardian_contact(1812345678.0), '01812345678')

    def test_other_numbers_from_numeric_cells_are_untouched(self):
        self.assertEqual(normalize_guardian_contact(880181234567), '880181234567')
        self.assertEqual(normalize_guardian_contact(1234567), '1234567')

    def test_valid_formats_pass_validation(self):
        for value in ('01812345678', '+8801812345678', '+880 1812-345678',
                      '01812 345678', '01812-345678'):
            validate_guardian_contact(value)

    def test_blank_passes_validation(self):
        # Blank is the field's own required/blank decision, not the
        # validator's — a blank guardian contact must not blow up here.
        validate_guardian_contact('')
        validate_guardian_contact(None)

    def test_invalid_numbers_are_rejected(self):
        for value in ('abc', '12345', 'call the office', '01812345678x',
                      'ph: 01812345678'):
            with self.assertRaises(ValidationError):
                validate_guardian_contact(value)


class StudentFormContactTests(TestCase):
    """The student add/edit form carries exactly one contact input."""

    def setUp(self):
        self.institution = Institution.objects.create(
            name='Guardian Form School', classes=INSTITUTION_CLASSES,
        )
        self.user = get_user_model().objects.create_superuser(
            username='guardian-admin', password='pw',
        )

    def _form_data(self, **overrides):
        data = {
            'institution': self.institution.pk,
            'name': 'Form Kid',
            'admission_class': '6',
            'section': 'A',
            'admission_year': 2026,
            'roll_no': 1,
            'gender': 'M',
            'religion': 'Islam',
            'father_name': 'Father',
            'guardian_contact_no': '01812345678',
            'status': 'ACTIVE',
            'group': '',
        }
        data.update(overrides)
        return data

    def test_legacy_contact_field_is_not_on_the_form(self):
        form = StudentForm(user=self.user)
        self.assertNotIn('contact_no', form.fields)
        self.assertIn('guardian_contact_no', form.fields)

    def test_valid_guardian_contact_saves_with_leading_zero(self):
        form = StudentForm(self._form_data(), user=self.user)
        self.assertTrue(form.is_valid(), form.errors)
        student = form.save()
        student.refresh_from_db()
        self.assertEqual(student.guardian_contact_no, '01812345678')

    def test_bangla_digits_are_normalised_on_save(self):
        form = StudentForm(self._form_data(guardian_contact_no='০১৮১২৩৪৫৬৭৮'),
                           user=self.user)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().guardian_contact_no, '01812345678')

    def test_blank_guardian_contact_is_rejected(self):
        # The guardian contact number is the single primary contact — a
        # student cannot be saved without one.
        form = StudentForm(self._form_data(guardian_contact_no=''), user=self.user)
        self.assertFalse(form.is_valid())
        self.assertIn('guardian_contact_no', form.errors)

    def test_invalid_guardian_contact_is_rejected(self):
        form = StudentForm(self._form_data(guardian_contact_no='not-a-phone'),
                           user=self.user)
        self.assertFalse(form.is_valid())
        self.assertIn('guardian_contact_no', form.errors)

    def test_form_field_is_required(self):
        form = StudentForm(user=self.user)
        self.assertTrue(form.fields['guardian_contact_no'].required)

    def test_add_student_page_has_one_contact_input(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('add_student'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'id_contact_no')
        self.assertNotContains(response, "Student's Contact No")
        self.assertContains(response, 'id_guardian_contact_no')
        self.assertContains(response, 'Guardian Contact Number')

    def test_student_detail_page_shows_the_guardian_contact(self):
        student = Student.objects.create(
            institution=self.institution, student_id='D001', name='Detail Kid',
            admission_class='6', section='A', admission_year=2026,
            guardian_contact_no='01812345678',
        )
        self.client.force_login(self.user)
        response = self.client.get(reverse('student_detail', args=[student.pk]))
        self.assertContains(response, 'Guardian Contact Number')
        self.assertContains(response, '01812345678')
        self.assertNotContains(response, '<th>Contact No</th>')


class AdmissionFormContactTests(TestCase):
    """The public and internal admission forms carry exactly one contact."""

    def setUp(self):
        self.institution = Institution.objects.create(
            name='Admission Contact School', classes=INSTITUTION_CLASSES,
        )
        self.user = get_user_model().objects.create_superuser(
            username='admission-contact-admin', password='pw',
        )

    def _form_data(self, **overrides):
        data = {
            'institution': self.institution.pk,
            'applicant_name': 'Applicant Kid',
            'date_of_birth': '2014-01-01',
            'gender': 'M',
            'religion': 'Islam',
            'applicant_address': 'Village',
            'guardian_name': 'Guardian',
            'guardian_relation': 'Father',
            'guardian_contact_no': '01812345678',
            'guardian_address': 'Village',
            'requested_class': '6',
            'requested_section': 'A',
            'session': '2026-2027',
        }
        data.update(overrides)
        return data

    def test_legacy_applicant_contact_field_is_not_on_the_form(self):
        form = AdmissionApplicationForm()
        self.assertNotIn('applicant_contact_no', form.fields)
        self.assertIn('guardian_contact_no', form.fields)

    def test_valid_submission_stores_guardian_contact_with_leading_zero(self):
        form = AdmissionApplicationForm(self._form_data())
        self.assertTrue(form.is_valid(), form.errors)
        application = form.save()
        application.refresh_from_db()
        self.assertEqual(application.guardian_contact_no, '01812345678')

    def test_guardian_contact_is_required(self):
        form = AdmissionApplicationForm(self._form_data(guardian_contact_no=''))
        self.assertFalse(form.is_valid())
        self.assertIn('guardian_contact_no', form.errors)

    def test_invalid_guardian_contact_is_rejected(self):
        form = AdmissionApplicationForm(self._form_data(guardian_contact_no='123'))
        self.assertFalse(form.is_valid())
        self.assertIn('guardian_contact_no', form.errors)

    def test_bangla_digits_are_normalised_on_the_public_form(self):
        form = AdmissionApplicationForm(self._form_data(guardian_contact_no='০১৮১২৩৪৫৬৭৮'))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().guardian_contact_no, '01812345678')

    def test_public_form_page_has_one_contact_input(self):
        response = self.client.get(reverse('public_admission_apply'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'id_applicant_contact_no')
        self.assertContains(response, 'id_guardian_contact_no')

    def test_internal_form_page_has_one_contact_input(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('admission'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'id_applicant_contact_no')
        self.assertContains(response, 'id_guardian_contact_no')


class StudentImportContactTests(TestCase):
    """The Excel import accepts the new single-contact template and the old
    two-column template, and keeps leading zeros."""

    def setUp(self):
        self.institution = Institution.objects.create(
            name='Import Contact School', classes=INSTITUTION_CLASSES,
        )
        self.user = get_user_model().objects.create_superuser(
            username='import-contact-admin', password='pw',
        )
        self.client.force_login(self.user)

    def _upload(self, headers, rows):
        book = Workbook()
        sheet = book.active
        sheet.append(headers)
        for row in rows:
            sheet.append(row)
        buffer = BytesIO()
        book.save(buffer)
        buffer.seek(0)
        return self.client.post(reverse('import_students'), {
            'excel_file': SimpleUploadedFile('students.xlsx', buffer.getvalue()),
        }, follow=True)

    def _new_template_headers(self):
        return [
            'Institution', 'Name', 'Admission Class', 'Section',
            'Admission Year', 'Roll No', 'Gender', 'Religion',
            "Father's Name", 'Guardian Contact Number', 'Group',
        ]

    def _legacy_template_headers(self):
        return [
            'Institution', 'Name', 'Admission Class', 'Section',
            'Admission Year', 'Roll No', 'Gender', 'Religion',
            "Father's Name", 'Contact No', 'Guardian Contact No', 'Group',
        ]

    def test_new_template_imports_guardian_contact_as_text(self):
        response = self._upload(self._new_template_headers(), [[
            self.institution.name, 'New Template Kid', '6', 'A', 2026, 1,
            'Male', 'Islam', 'Father', '01812345678', '',
        ]])
        self.assertEqual(response.status_code, 200)
        student = Student.objects.get(name='New Template Kid')
        self.assertEqual(student.guardian_contact_no, '01812345678')

    def test_legacy_template_still_imports(self):
        # A sheet downloaded from the old template has both contact columns;
        # the guardian column remains the single source.
        response = self._upload(self._legacy_template_headers(), [[
            self.institution.name, 'Legacy Template Kid', '6', 'A', 2026, 2,
            'Male', 'Islam', 'Father', '01700000000', '01812345678', '',
        ]])
        self.assertEqual(response.status_code, 200)
        student = Student.objects.get(name='Legacy Template Kid')
        self.assertEqual(student.guardian_contact_no, '01812345678')

    def test_legacy_contact_used_when_guardian_column_is_blank(self):
        # Old files where only the "Contact No" column was filled must not
        # lose their number: it becomes the guardian contact.
        response = self._upload(self._legacy_template_headers(), [[
            self.institution.name, 'Fallback Kid', '6', 'A', 2026, 3,
            'Male', 'Islam', 'Father', '01711111111', '', '',
        ]])
        self.assertEqual(response.status_code, 200)
        student = Student.objects.get(name='Fallback Kid')
        self.assertEqual(student.guardian_contact_no, '01711111111')

    def test_numeric_excel_cell_gets_its_leading_zero_back(self):
        # Typing 01812345678 into a General-format Excel cell stores the
        # number 1812345678; the importer restores the leading zero.
        response = self._upload(self._new_template_headers(), [[
            self.institution.name, 'Numeric Cell Kid', '6', 'A', 2026, 4,
            'Male', 'Islam', 'Father', 1812345678, '',
        ]])
        self.assertEqual(response.status_code, 200)
        student = Student.objects.get(name='Numeric Cell Kid')
        self.assertEqual(student.guardian_contact_no, '01812345678')

    def test_invalid_contact_skips_the_row_with_an_error(self):
        response = self._upload(self._new_template_headers(), [
            [self.institution.name, 'Bad Phone Kid', '6', 'A', 2026, 5,
             'Male', 'Islam', 'Father', 'call office', ''],
            [self.institution.name, 'Good Phone Kid', '6', 'A', 2026, 6,
             'Male', 'Islam', 'Father', '01812345678', ''],
        ])
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Student.objects.filter(name='Bad Phone Kid').exists())
        student = Student.objects.get(name='Good Phone Kid')
        self.assertEqual(student.guardian_contact_no, '01812345678')
        messages = [str(m) for m in response.context['messages']]
        self.assertTrue(any('invalid guardian contact number' in m for m in messages))

    def test_missing_contact_skips_the_row_with_an_error(self):
        # The guardian contact number is required — a row without one (in
        # neither the guardian nor the legacy column) is skipped.
        response = self._upload(self._new_template_headers(), [
            [self.institution.name, 'No Phone Kid', '6', 'A', 2026, 7,
             'Male', 'Islam', 'Father', '', ''],
            [self.institution.name, 'Good Phone Kid', '6', 'A', 2026, 8,
             'Male', 'Islam', 'Father', '01812345678', ''],
        ])
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Student.objects.filter(name='No Phone Kid').exists())
        student = Student.objects.get(name='Good Phone Kid')
        self.assertEqual(student.guardian_contact_no, '01812345678')
        messages = [str(m) for m in response.context['messages']]
        self.assertTrue(any('guardian contact number is missing' in m for m in messages))

    def test_re_import_backfills_a_missing_guardian_contact(self):
        # A student created before the contact became required can still
        # have a blank guardian number. Re-importing a row that matches them
        # and carries the number fills it in (never overwrites one).
        Student.objects.create(
            institution=self.institution, student_id='RB001', name='Backfill Kid',
            admission_class='6', section='A', admission_year=2026, roll_no=8,
            guardian_contact_no='',
        )
        response = self._upload(self._new_template_headers(), [[
            self.institution.name, 'Backfill Kid', '6', 'A', 2026, 8,
            'Male', 'Islam', 'Father', '01812345678', '',
        ]])
        student = Student.objects.get(name='Backfill Kid')
        self.assertEqual(student.guardian_contact_no, '01812345678')
        messages = [str(m) for m in response.context['messages']]
        self.assertTrue(
            any('guardian contact number filled in' in m for m in messages))

    def test_re_import_never_overwrites_an_existing_guardian_contact(self):
        row = [self.institution.name, 'Keep Number Kid', '6', 'A', 2026, 9,
               'Male', 'Islam', 'Father', '01812345678', '']
        self._upload(self._new_template_headers(), [row])
        row[9] = '01999999999'
        self._upload(self._new_template_headers(), [row])
        student = Student.objects.get(name='Keep Number Kid')
        self.assertEqual(student.guardian_contact_no, '01812345678')

    def test_headerless_sheet_falls_back_to_the_legacy_column_order(self):
        # A hand-made sheet whose header row is unrecognisable used to work
        # positionally; it still must.
        response = self._upload(
            ['School', 'Pupil', 'Grade', 'Sec', 'Year', 'Roll',
             'M/F', 'Faith', 'Dad', 'Ph', 'Guard Ph', 'Grp'],
            [[self.institution.name, 'Positional Kid', '6', 'A', 2026, 10,
              'Male', 'Islam', 'Father', '01700000000', '01812345678', '']],
        )
        self.assertEqual(response.status_code, 200)
        student = Student.objects.get(name='Positional Kid')
        self.assertEqual(student.guardian_contact_no, '01812345678')

    def test_import_template_download_has_the_single_contact_column(self):
        response = self.client.get(reverse('download_import_template'))
        self.assertEqual(response.status_code, 200)
        sheet = load_workbook(BytesIO(response.content)).active
        headers = [cell.value for cell in next(sheet.iter_rows(max_row=1))]
        self.assertIn('Guardian Contact Number', headers)
        self.assertNotIn('Contact No', headers)
        self.assertNotIn('Guardian Contact No', headers)
        # The contact column is pre-formatted as text so Excel keeps a
        # typed leading zero.
        contact_column = headers.index('Guardian Contact Number') + 1
        self.assertEqual(sheet.cell(row=1, column=contact_column).number_format, '@')
        self.assertEqual(sheet.cell(row=50, column=contact_column).number_format, '@')


class ContactExportTests(TestCase):
    """Exports carry the one canonical contact column."""

    def setUp(self):
        self.institution = Institution.objects.create(
            name='Export Contact School', classes=INSTITUTION_CLASSES,
        )
        self.user = get_user_model().objects.create_superuser(
            username='export-contact-admin', password='pw',
        )
        self.client.force_login(self.user)
        self.student = Student.objects.create(
            institution=self.institution, student_id='E001', name='Export Kid',
            admission_class='6', section='A', admission_year=2026, roll_no=1,
            guardian_contact_no='01812345678',
        )
        self.application = AdmissionApplication.objects.create(
            institution=self.institution, applicant_name='Export Applicant',
            guardian_name='Export Guardian',
            guardian_contact_no='01812345678', requested_class='6',
            requested_section='A', session='2026-2027',
        )

    def test_student_list_export_has_single_contact_column(self):
        response = self.client.get(reverse('download_student_list'))
        self.assertEqual(response.status_code, 200)
        sheet = load_workbook(BytesIO(response.content)).active
        headers = [cell.value for cell in next(sheet.iter_rows(max_row=1))]
        self.assertIn('Guardian Contact Number', headers)
        self.assertNotIn('Contact No', headers)
        self.assertNotIn('Guardian Contact No', headers)
        row = list(next(sheet.iter_rows(min_row=2, values_only=True)))
        self.assertEqual(row[headers.index('Guardian Contact Number')], '01812345678')

    def test_admission_sheet_export_has_single_contact_column(self):
        response = self.client.get(reverse('download_admission_sheet'))
        self.assertEqual(response.status_code, 200)
        workbook = load_workbook(BytesIO(response.content))
        sheet = workbook[workbook.sheetnames[0]]
        headers = [cell.value for cell in next(sheet.iter_rows(max_row=1))]
        self.assertIn('Guardian Contact Number', headers)
        self.assertNotIn('Contact No', headers)
        row = list(next(sheet.iter_rows(min_row=2, values_only=True)))
        self.assertEqual(row[headers.index('Guardian Contact Number')], '01812345678')


class EnrolmentContactTests(TestCase):
    """Approving payment creates the student with the guardian contact."""

    def setUp(self):
        self.institution = Institution.objects.create(
            name='Enrolment Contact School', classes=INSTITUTION_CLASSES,
        )
        self.user = get_user_model().objects.create_superuser(
            username='enrolment-contact-admin', password='pw',
        )
        self.client.force_login(self.user)
        self.application = AdmissionApplication.objects.create(
            institution=self.institution, applicant_name='Enrolment Kid',
            guardian_name='Enrolment Guardian',
            guardian_contact_no='01812345678', requested_class='6',
            requested_section='A', session='2026-2027',
            status='ACCOUNT_PENDING', payment_amount=1500,
            payment_date=date(2026, 9, 1),
        )

    def test_enrolled_student_carries_the_guardian_contact(self):
        response = self.client.post(
            reverse('accounts_approve_payment', args=[self.application.pk]),
            {'payment_amount': '1500.00', 'payment_date': '2026-09-01',
             'payment_purpose': 'Admission Fee', 'account_remarks': 'Paid'},
        )
        self.assertEqual(response.status_code, 302)
        self.application.refresh_from_db()
        student = self.application.enrolled_student
        self.assertEqual(student.guardian_contact_no, '01812345678')


class GuardianContactSearchTests(TestCase):
    """The student search finds a student by guardian contact (and, during
    the transition, by the legacy contact too)."""

    def setUp(self):
        self.institution = Institution.objects.create(
            name='Search Contact School', classes=INSTITUTION_CLASSES,
        )
        self.user = get_user_model().objects.create_superuser(
            username='search-contact-admin', password='pw',
        )
        self.client.force_login(self.user)

    def test_search_by_guardian_contact(self):
        Student.objects.create(
            institution=self.institution, student_id='SE001', name='Search Kid',
            admission_class='6', section='A', admission_year=2026,
            guardian_contact_no='01812345678',
        )
        response = self.client.get(reverse('student_list'), {'q': '01812345678'})
        self.assertContains(response, 'Search Kid')


class LegacyContactDropMigrationTests(TransactionTestCase):
    """Migration 0040 finishes the unification, tested end to end against
    the real migration chain: it backfills blank guardian numbers from the
    legacy column, archives every legacy number that differs from the
    guardian number to AuditLog, and only then drops the legacy columns."""

    def _migrate(self, target):
        executor = MigrationExecutor(connection)
        executor.migrate([('students', target)])
        return executor

    def test_drop_backfills_archives_and_removes_the_columns(self):
        # Roll the schema back to the last state where the legacy columns
        # exist (0039 applied) and seed data with the historical models.
        executor = self._migrate('0039_unify_guardian_contact')
        state = executor.loader.project_state(
            [('students', '0039_unify_guardian_contact')])
        OldInstitution = state.apps.get_model('students', 'Institution')
        OldStudent = state.apps.get_model('students', 'Student')
        OldApplication = state.apps.get_model('students', 'AdmissionApplication')

        institution = OldInstitution.objects.create(
            name='Drop Migration School', classes='6,9')
        conflict = OldStudent.objects.create(
            institution=institution, student_id='X001', name='Conflict Kid',
            admission_class='6', section='A', admission_year=2026,
            contact_no='01700000000', guardian_contact_no='01900000000',
        )
        legacy_only = OldStudent.objects.create(
            institution=institution, student_id='X002', name='Legacy Only Kid',
            admission_class='6', section='A', admission_year=2026,
            contact_no='01711111111', guardian_contact_no='',
        )
        OldStudent.objects.create(
            institution=institution, student_id='X003', name='Same Number Kid',
            admission_class='6', section='A', admission_year=2026,
            contact_no='01812345678', guardian_contact_no='01812345678',
        )
        OldApplication.objects.create(
            institution=institution, applicant_name='Conflict App',
            applicant_contact_no='01800000000', guardian_name='Guardian',
            guardian_contact_no='01900000000', requested_class='6',
            session='2026-2027',
        )

        try:
            # Forward through 0040 (archive + drop) and 0041 (required).
            self._migrate('0041_student_guardian_contact_required')

            # The blank guardian number was backfilled from the legacy
            # column; the conflicting guardian number was NOT overwritten.
            self.assertEqual(
                Student.objects.get(pk=legacy_only.pk).guardian_contact_no,
                '01711111111')
            self.assertEqual(
                Student.objects.get(pk=conflict.pk).guardian_contact_no,
                '01900000000')

            # The legacy columns are gone from the model and the form.
            with self.assertRaises(FieldDoesNotExist):
                Student._meta.get_field('contact_no')
            with self.assertRaises(FieldDoesNotExist):
                AdmissionApplication._meta.get_field('applicant_contact_no')

            # The differing legacy numbers were archived to AuditLog before
            # the columns dropped; matching numbers were not (they live on
            # in the guardian column).
            student_archive = AuditLog.objects.get(
                action='legacy_contact_dropped', model_name='Student')
            archived = {
                row['identifier']: row for row in student_archive.details['dropped_rows']
            }
            self.assertIn('X001', archived)
            self.assertEqual(archived['X001']['legacy_contact'], '01700000000')
            self.assertEqual(archived['X001']['guardian_contact'], '01900000000')
            self.assertNotIn('X002', archived)  # backfilled, not dropped
            self.assertNotIn('X003', archived)  # same number: nothing lost
            app_archive = AuditLog.objects.get(
                action='legacy_contact_dropped', model_name='AdmissionApplication')
            self.assertEqual(
                app_archive.details['dropped_rows'][0]['legacy_contact'],
                '01800000000')
        finally:
            # Never leave the schema rolled back for the rest of the suite.
            try:
                self._migrate('0041_student_guardian_contact_required')
            except Exception:
                pass


class ConflictReportAfterDropTests(TestCase):
    """Once migration 0040 has removed the legacy columns, the conflict
    report explains that and points at the archived AuditLog entries."""

    def test_report_points_at_the_audit_log(self):
        out = StringIO()
        call_command('contact_conflict_report', stdout=out)
        report = out.getvalue()
        self.assertIn('already', report)
        self.assertIn('legacy_contact_dropped', report)
