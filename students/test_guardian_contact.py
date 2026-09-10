"""Tests for the single canonical guardian contact number.

One primary contact per student / admission application:
"Guardian Contact Number / অভিভাবকের যোগাযোগ নম্বর" (Student.guardian_contact_no
and AdmissionApplication.guardian_contact_no).

Covers:
* normalisation — leading zero kept, Bangla digits, numeric Excel cells;
* validation — blank/invalid numbers, supported formats;
* the forms and pages carrying exactly one contact input;
* the Excel import (new single-column template + legacy two-column
  template) and the exports;
* the enrolment hand-off (application -> student);
* the safe backfill migration and the dry-run conflict report.
"""
import importlib.util
import pathlib
from datetime import date
from io import BytesIO, StringIO

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from .forms import AdmissionApplicationForm, StudentForm
from .models import (
    AdmissionApplication, Institution, Student,
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
        self.assertEqual(student.contact_no, '')

    def test_bangla_digits_are_normalised_on_save(self):
        form = StudentForm(self._form_data(guardian_contact_no='০১৮১২৩৪৫৬৭৮'),
                           user=self.user)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().guardian_contact_no, '01812345678')

    def test_blank_guardian_contact_is_allowed(self):
        form = StudentForm(self._form_data(guardian_contact_no=''), user=self.user)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().guardian_contact_no, '')

    def test_invalid_guardian_contact_is_rejected(self):
        form = StudentForm(self._form_data(guardian_contact_no='not-a-phone'),
                           user=self.user)
        self.assertFalse(form.is_valid())
        self.assertIn('guardian_contact_no', form.errors)

    def test_editing_does_not_touch_the_legacy_column(self):
        # A legacy row still carries its old contact_no value; saving the
        # edit form must not clear or copy it (the backfill migration and
        # the conflict report own that job).
        student = Student.objects.create(
            institution=self.institution, student_id='L001', name='Legacy Kid',
            admission_class='6', section='A', admission_year=2026,
            contact_no='01700000000', guardian_contact_no='01900000000',
        )
        form = StudentForm(self._form_data(), instance=student, user=self.user)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        student.refresh_from_db()
        self.assertEqual(student.contact_no, '01700000000')
        self.assertEqual(student.guardian_contact_no, '01812345678')

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
        self.assertEqual(application.applicant_contact_no, '')

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
        self.assertEqual(student.contact_no, '')

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

    def test_blank_contact_is_allowed_on_import(self):
        response = self._upload(self._new_template_headers(), [[
            self.institution.name, 'No Phone Kid', '6', 'A', 2026, 7,
            'Male', 'Islam', 'Father', '', '',
        ]])
        self.assertEqual(response.status_code, 200)
        student = Student.objects.get(name='No Phone Kid')
        self.assertEqual(student.guardian_contact_no, '')

    def test_re_import_backfills_a_missing_guardian_contact(self):
        # First file had no contact; the re-run carries it and must fill the
        # existing student in (same treatment the group column gets).
        self._upload(self._new_template_headers(), [[
            self.institution.name, 'Backfill Kid', '6', 'A', 2026, 8,
            'Male', 'Islam', 'Father', '', '',
        ]])
        student = Student.objects.get(name='Backfill Kid')
        self.assertEqual(student.guardian_contact_no, '')
        response = self._upload(self._new_template_headers(), [[
            self.institution.name, 'Backfill Kid', '6', 'A', 2026, 8,
            'Male', 'Islam', 'Father', '01812345678', '',
        ]])
        student.refresh_from_db()
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
            applicant_contact_no='01700000000', guardian_name='Export Guardian',
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
            applicant_contact_no='01700000000', guardian_name='Enrolment Guardian',
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
        self.assertEqual(student.contact_no, '')


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

    def test_search_still_finds_a_legacy_only_number(self):
        # Pre-migration rows can hold the number only in the legacy column.
        Student.objects.create(
            institution=self.institution, student_id='SE002', name='Legacy Search Kid',
            admission_class='6', section='A', admission_year=2026,
            contact_no='01700000000',
        )
        response = self.client.get(reverse('student_list'), {'q': '01700000000'})
        self.assertContains(response, 'Legacy Search Kid')


class BackfillMigrationTests(TestCase):
    """Migration 0039 copies the legacy contact into guardian_contact_no
    only where the guardian number is blank — never over one."""

    def _load_migration(self):
        path = (pathlib.Path(__file__).parent / 'migrations'
                / '0039_unify_guardian_contact.py')
        spec = importlib.util.spec_from_file_location(
            'unify_guardian_contact_migration', path,
        )
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        return migration

    def setUp(self):
        self.institution = Institution.objects.create(
            name='Backfill School', classes=INSTITUTION_CLASSES,
        )

    class _AppsShim:
        """Stands in for the migration's historical app registry."""

        @staticmethod
        def get_model(app_label, model_name):
            return {'Student': Student,
                    'AdmissionApplication': AdmissionApplication}[model_name]

    def test_blank_guardian_gets_the_legacy_number(self):
        Student.objects.create(
            institution=self.institution, student_id='B001', name='Backfill Me',
            admission_class='6', section='A', admission_year=2026,
            contact_no='01700000000', guardian_contact_no='',
        )
        self._load_migration().backfill_guardian_contact_from_legacy(
            self._AppsShim, None)
        student = Student.objects.get(student_id='B001')
        self.assertEqual(student.guardian_contact_no, '01700000000')
        self.assertEqual(student.contact_no, '01700000000')

    def test_existing_guardian_number_is_never_overwritten(self):
        Student.objects.create(
            institution=self.institution, student_id='B002', name='Conflict Me',
            admission_class='6', section='A', admission_year=2026,
            contact_no='01700000000', guardian_contact_no='01900000000',
        )
        self._load_migration().backfill_guardian_contact_from_legacy(
            self._AppsShim, None)
        student = Student.objects.get(student_id='B002')
        self.assertEqual(student.guardian_contact_no, '01900000000')
        self.assertEqual(student.contact_no, '01700000000')

    def test_both_blank_stays_blank(self):
        Student.objects.create(
            institution=self.institution, student_id='B003', name='Nothing Me',
            admission_class='6', section='A', admission_year=2026,
        )
        self._load_migration().backfill_guardian_contact_from_legacy(
            self._AppsShim, None)
        student = Student.objects.get(student_id='B003')
        self.assertEqual(student.guardian_contact_no, '')

    def test_application_blank_guardian_gets_the_applicant_number(self):
        AdmissionApplication.objects.create(
            institution=self.institution, applicant_name='Backfill App',
            applicant_contact_no='01800000000', guardian_name='Guardian',
            guardian_contact_no='', requested_class='6', session='2026-2027',
        )
        self._load_migration().backfill_guardian_contact_from_legacy(
            self._AppsShim, None)
        application = AdmissionApplication.objects.get(applicant_name='Backfill App')
        self.assertEqual(application.guardian_contact_no, '01800000000')

    def test_application_conflict_is_never_overwritten(self):
        AdmissionApplication.objects.create(
            institution=self.institution, applicant_name='Conflict App',
            applicant_contact_no='01800000000', guardian_name='Guardian',
            guardian_contact_no='01900000000', requested_class='6',
            session='2026-2027',
        )
        self._load_migration().backfill_guardian_contact_from_legacy(
            self._AppsShim, None)
        application = AdmissionApplication.objects.get(applicant_name='Conflict App')
        self.assertEqual(application.guardian_contact_no, '01900000000')


class ConflictReportCommandTests(TestCase):
    """contact_conflict_report is a dry run: it reports, it never writes."""

    def setUp(self):
        self.institution = Institution.objects.create(
            name='Conflict Report School', classes=INSTITUTION_CLASSES,
        )
        Student.objects.create(
            institution=self.institution, student_id='C001',
            name='Conflict Kid', admission_class='6', section='A',
            admission_year=2026,
            contact_no='01700000000', guardian_contact_no='01900000000',
        )
        Student.objects.create(
            institution=self.institution, student_id='C002',
            name='Backfill Kid', admission_class='6', section='A',
            admission_year=2026,
            contact_no='01700000000', guardian_contact_no='',
        )
        AdmissionApplication.objects.create(
            institution=self.institution, applicant_name='Conflict App',
            applicant_contact_no='01800000000', guardian_name='Guardian',
            guardian_contact_no='01900000000', requested_class='6',
            session='2026-2027',
        )

    def test_report_lists_conflicts_and_backfill_counts_without_writing(self):
        out = StringIO()
        call_command('contact_conflict_report', stdout=out)
        report = out.getvalue()

        self.assertIn('C001', report)
        self.assertIn('Conflict Kid', report)
        self.assertIn('Conflict App', report)
        self.assertIn('CONFLICT: 1 row(s)', report)
        self.assertIn('BACKFILL: 1 row(s)', report)

        # Dry run: nothing changed.
        student = Student.objects.get(student_id='C001')
        self.assertEqual(student.guardian_contact_no, '01900000000')
        backfill = Student.objects.get(student_id='C002')
        self.assertEqual(backfill.guardian_contact_no, '')

    def test_matching_numbers_are_not_reported_as_conflicts(self):
        Student.objects.create(
            institution=self.institution, student_id='C003',
            name='Matching Kid', admission_class='6', section='A',
            admission_year=2026,
            contact_no='01812345678', guardian_contact_no='01812345678',
        )
        out = StringIO()
        call_command('contact_conflict_report', stdout=out)
        report = out.getvalue()
        self.assertNotIn('Matching Kid', report.split('Admission applications')[0])
        self.assertIn('same number in both columns', report)
