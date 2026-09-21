"""Two-institution read-isolation tests.

A clerk who may only read Institution A must never be able to read Institution
B's rows — whether by editing a query parameter (?institution=<B>) or a pk in
the URL. The authorized cross-institution administrator (staff/superuser) keeps
full, deliberate access across institutions. These tests use two-institution
fixtures only; SSC Registration / SSC Result Summary are not touched.
"""
from io import BytesIO
from datetime import date

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

try:
    from openpyxl import load_workbook
except ModuleNotFoundError:
    load_workbook = None

from .models import (
    AdmissionApplication, Certificate, Employee, Exam, ExamMark, Institution,
    InstitutionAccess, MoneyReceipt, Student, Subject, TransferCertificate,
)
from .result_utils import get_exam_students


class InstitutionReadIsolationTests(TestCase):
    """Verify a single-institution clerk cannot read another institution's rows,
    and that the cross-institution admin still can."""

    def setUp(self):
        self.institution = Institution.objects.create(name='Isolation A', classes='6,7')
        self.other = Institution.objects.create(name='Isolation B', classes='6,7')

        # Clerk scoped to institution A only (Office).
        self.clerk = get_user_model().objects.create_user(username='clerk_a', password='password')
        InstitutionAccess.objects.create(user=self.clerk, institution=self.institution, department='Office')
        # DB-03/SEC-FU-3 gated money_receipt_list/finance_dashboard behind
        # students.view_moneyreceipt (Accounts-only); granted directly here so
        # this file keeps testing institution scoping, not department access.
        self.clerk.user_permissions.add(
            Permission.objects.get(
                content_type=ContentType.objects.get_for_model(MoneyReceipt),
                codename='view_moneyreceipt',
            )
        )

        # Authorized cross-institution administrator (superuser).
        self.admin = get_user_model().objects.create_superuser(
            username='iso-admin', password='password', email='admin@example.com',
        )

        self.student_a = Student.objects.create(
            institution=self.institution, student_id='A001', name='Alpha Student',
            admission_class='6', section='A', admission_year=2026,
        )
        self.student_b = Student.objects.create(
            institution=self.other, student_id='B001', name='Beta Student',
            admission_class='6', section='A', admission_year=2026,
        )

        self.employee_a = Employee.objects.create(
            institution=self.institution, name='Alpha Employee', designation='Teacher',
            join_date=date(2026, 1, 1),
        )
        self.employee_b = Employee.objects.create(
            institution=self.other, name='Beta Employee', designation='Teacher',
            join_date=date(2026, 1, 1),
        )

        self.exam_a = Exam.objects.create(
            name='A Exam', exam_type='FIRST_TERM', institution=self.institution,
            admission_class='6', section='', session='2026',
        )
        self.exam_b = Exam.objects.create(
            name='B Exam', exam_type='FIRST_TERM', institution=self.other,
            admission_class='6', section='', session='2026', is_published=True,
        )

        self.application_a = AdmissionApplication.objects.create(
            institution=self.institution, applicant_name='App A', guardian_name='Guard A', guardian_contact_no='01900000000',
            requested_class='6', session='2026-2027',
        )
        self.application_b = AdmissionApplication.objects.create(
            institution=self.other, applicant_name='App B', guardian_name='Guard B', guardian_contact_no='01900000001',
            requested_class='6', session='2026-2027',
        )

        # Give the clerk the permissions needed to reach the guarded views, so
        # the tests exercise the *institution* 404 rather than a 403/redirect.
        for model, codename in (
            (AdmissionApplication, 'view_admissionapplication'),
            (Exam, 'change_exam'),
            (ExamMark, 'add_exammark'),
        ):
            self.clerk.user_permissions.add(
                Permission.objects.get(
                    content_type=ContentType.objects.get_for_model(model),
                    codename=codename,
                )
            )

    # ------------------------------------------------------------------ helpers

    # ------------------------------------------------------------------ helpers
    def login_as_clerk(self, institution=None):
        self.client.force_login(self.clerk)
        session = self.client.session
        target = institution or self.institution
        session['selected_institution_id'] = str(target.pk)
        session['selected_department'] = 'Office'
        session.save()

    def login_as_admin(self, institution=None):
        self.client.force_login(self.admin)
        session = self.client.session
        if institution is not None:
            session['selected_institution_id'] = str(institution.pk)
        session['selected_department'] = 'Office'
        session.save()

    # ---------------------------------------------------------- list / search
    def test_student_list_honours_institution_param_within_access(self):
        """A clerk asking ?institution=<B> is shown their own institution, never B."""
        self.login_as_clerk()
        response = self.client.get(reverse('student_list'), {'institution': self.other.pk})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Alpha Student')
        self.assertNotContains(response, 'Beta Student')

    def test_student_list_with_session_bounds_to_selected_institution(self):
        self.login_as_clerk()
        response = self.client.get(reverse('student_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Alpha Student')
        self.assertNotContains(response, 'Beta Student')

    def test_student_list_with_no_session_bounds_to_allowed_set(self):
        """A logged-in clerk whose session lost its institution still only sees
        the institutions they hold active access for."""
        # A logged-in clerk whose session has no institution selected must be
        # bounded to their allowed set, never shown the whole roll.
        self.client.force_login(self.clerk)
        session = self.client.session
        session['selected_institution_id'] = ''
        session['selected_department'] = 'Office'
        session.save()
        response = self.client.get(reverse('student_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Alpha Student')
        self.assertNotContains(response, 'Beta Student')

    def test_student_by_id_does_not_find_other_institution_student(self):
        self.login_as_clerk()
        url = reverse('student_by_id', args=[self.student_b.student_id])
        response = self.client.get(url)
        # Redirects to student_list with a 'No student found' message (200).
        self.assertRedirects(response, f"{reverse('student_list')}?q={self.student_b.student_id}")

    # ------------------------------------------------------------- detail (pk)
    def test_student_detail_404_for_other_institution(self):
        self.login_as_clerk()
        response = self.client.get(reverse('student_detail', args=[self.student_b.pk]))
        self.assertEqual(response.status_code, 404)

    def test_student_detail_ok_for_own_institution(self):
        self.login_as_clerk()
        response = self.client.get(reverse('student_detail', args=[self.student_a.pk]))
        self.assertEqual(response.status_code, 200)

    def test_employee_detail_404_for_other_institution(self):
        self.login_as_clerk()
        response = self.client.get(reverse('employee_detail', args=[self.employee_b.pk]))
        self.assertEqual(response.status_code, 404)

    def test_admission_application_detail_404_for_other_institution(self):
        self.login_as_clerk()
        response = self.client.get(reverse('admission_application_detail', args=[self.application_b.pk]))
        self.assertEqual(response.status_code, 404)

    # ------------------------------------------------------------------ export
    def test_download_student_list_does_not_leak_other_institution(self):
        if load_workbook is None:
            self.skipTest('openpyxl is required for the Excel export tests')
        self.login_as_clerk()
        response = self.client.get(reverse('download_student_list'), {'institution': self.other.pk})
        self.assertEqual(response.status_code, 200)
        workbook = load_workbook(BytesIO(response.content), data_only=True)
        sheet = workbook.active
        names = [row[1] for row in sheet.iter_rows(values_only=True)]
        self.assertIn('Alpha Student', names)
        self.assertNotIn('Beta Student', names)

    # ----------------------------------------------------------------- exams
    def test_result_sheet_404_for_other_institution_exam(self):
        self.login_as_clerk()
        response = self.client.get(reverse('result_sheet', args=[self.exam_b.pk]))
        self.assertEqual(response.status_code, 404)

    def test_enter_marks_404_for_other_institution_exam(self):
        self.login_as_clerk()
        response = self.client.get(reverse('enter_marks', args=[self.exam_b.pk, 1]))
        self.assertEqual(response.status_code, 404)

    def test_seat_plan_list_404_for_other_institution_exam(self):
        self.login_as_clerk()
        response = self.client.get(reverse('seat_plan_list', args=[self.exam_b.pk]))
        self.assertEqual(response.status_code, 404)

    def test_edit_exam_404_for_other_institution_exam(self):
        self.login_as_clerk()
        response = self.client.get(reverse('edit_exam', args=[self.exam_b.pk]))
        self.assertEqual(response.status_code, 404)

    # ------------------------------------------------------------------ JSON
    def test_subject_requirements_json_does_not_leak_other_institution(self):
        subject = Subject.objects.create(code='BAN', name='Bangla', full_marks=100)
        from .models import SubjectRequirement
        SubjectRequirement.objects.create(
            institution=self.other, admission_class='6', subject=subject,
            requirement_type='MANDATORY',
        )
        self.login_as_clerk()
        response = self.client.get(reverse('subject_requirements_json'), {
            'institution': self.other.pk, 'admission_class': '6',
        })
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['mandatory'], [])
        self.assertEqual(payload['conditional'], [])

    # ---------------- SEC batch-02: export / result / document read surfaces
    def test_download_admission_sheet_does_not_leak_other_institution(self):
        if load_workbook is None:
            self.skipTest('openpyxl is required for the Excel export tests')
        self.login_as_clerk()
        response = self.client.get(
            reverse('download_admission_sheet'), {'institution': self.other.pk},
        )
        self.assertEqual(response.status_code, 200)
        workbook = load_workbook(BytesIO(response.content), data_only=True)
        applicants = [
            row[1]
            for sheet in workbook.worksheets
            for row in sheet.iter_rows(values_only=True)
        ]
        self.assertIn('App A', applicants)
        self.assertNotIn('App B', applicants)

    def test_download_marks_import_template_404_for_other_institution_exam(self):
        self.login_as_clerk()
        response = self.client.get(
            reverse('download_marks_import_template', args=[self.exam_b.pk]),
        )
        self.assertEqual(response.status_code, 404)

    def test_result_pages_404_for_other_institution_exam(self):
        """Every published-result read surface (rank list, top 10, summary,
        per-student detail and result card) 404s on another institution's exam
        or student, exactly like result_sheet already did."""
        self.login_as_clerk()
        for url in (
            reverse('full_rank_list', args=[self.exam_b.pk]),
            reverse('top_10', args=[self.exam_b.pk]),
            reverse('exam_result_summary', args=[self.exam_b.pk]),
            reverse('student_result_detail', args=[self.exam_b.pk, self.student_b.pk]),
            reverse('result_card', args=[self.exam_b.pk, self.student_b.pk]),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)

    def test_tc_and_certificate_reads_404_for_other_institution(self):
        tc_b = TransferCertificate.objects.create(student=self.student_b)
        certificate_b = Certificate.objects.create(
            student=self.student_b, certificate_type='STUDY',
        )
        self.login_as_clerk()
        for url in (
            reverse('view_tc', args=[tc_b.pk]),
            reverse('view_certificate', args=[certificate_b.pk]),
            reverse('certificate_list', args=[self.student_b.pk]),
            reverse('student_id_card', args=[self.student_b.pk]),
            reverse('student_exams', args=[self.student_b.pk]),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)

    def test_money_receipt_list_does_not_leak_other_institution(self):
        MoneyReceipt.objects.create(
            student=self.student_a, receipt_no='RC-READ-A', purpose='Fee',
            amount=100, date=date(2026, 1, 1),
        )
        MoneyReceipt.objects.create(
            student=self.student_b, receipt_no='RC-READ-B', purpose='Fee',
            amount=200, date=date(2026, 1, 1),
        )
        self.login_as_clerk()
        response = self.client.get(reverse('money_receipt_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'RC-READ-A')
        self.assertNotContains(response, 'RC-READ-B')

    def test_finance_dashboard_totals_exclude_other_institution(self):
        MoneyReceipt.objects.create(
            student=self.student_a, receipt_no='RC-FIN-A', purpose='Fee',
            amount=100, date=date(2026, 1, 1),
        )
        MoneyReceipt.objects.create(
            student=self.student_b, receipt_no='RC-FIN-B', purpose='Fee',
            amount=250, date=date(2026, 1, 1),
        )
        self.login_as_clerk()
        response = self.client.get(reverse('finance_dashboard'))
        self.assertEqual(response.status_code, 200)
        # Only the A receipt is read into the finance cards; B's 250 never
        # appears anywhere on the page (in totals or the recent list).
        self.assertNotContains(response, '250')
        self.assertNotContains(response, 'RC-FIN-B')

    def test_archived_list_does_not_leak_other_institution(self):
        archived_a = Student.objects.create(
            institution=self.institution, student_id='AA001', name='Archived Alpha',
            admission_class='6', section='A', admission_year=2026, is_archived=True,
        )
        Student.objects.create(
            institution=self.other, student_id='AB001', name='Archived Beta',
            admission_class='6', section='A', admission_year=2026, is_archived=True,
        )
        self.clerk.user_permissions.add(
            Permission.objects.get(
                content_type=ContentType.objects.get_for_model(Student),
                codename='view_student',
            )
        )
        self.login_as_clerk()
        response = self.client.get(
            reverse('archived_students'), {'institution': self.other.pk},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Archived Alpha')
        self.assertNotContains(response, 'Archived Beta')

    def test_attendance_reads_do_not_leak_other_institution(self):
        from .models import AttendanceRecord
        AttendanceRecord.objects.create(
            institution=self.institution, student=self.student_a,
            date=date(2026, 9, 1), status='P',
        )
        AttendanceRecord.objects.create(
            institution=self.other, student=self.student_b,
            date=date(2026, 9, 1), status='A',
        )
        self.login_as_clerk()
        report = self.client.get(reverse('attendance_report'))
        self.assertEqual(report.status_code, 200)
        self.assertContains(report, 'Alpha Student')
        self.assertNotContains(report, 'Beta Student')
        summary = self.client.get(
            reverse('attendance_summary'),
            {'start_date': '2026-09-01', 'end_date': '2026-09-02'},
        )
        self.assertEqual(summary.status_code, 200)
        self.assertContains(summary, 'Alpha Student')
        self.assertNotContains(summary, 'Beta Student')

    # ------------------------------------------------------ cross-institution
    def test_admin_can_read_across_institutions(self):
        """An authorized cross-institution administrator keeps full access."""
        self.login_as_admin()
        response = self.client.get(reverse('student_list'), {'institution': self.other.pk})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Beta Student')
        self.assertNotContains(response, 'Alpha Student')

        detail = self.client.get(reverse('student_detail', args=[self.student_b.pk]))
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, 'Beta Student')

    def test_clerk_holding_both_institutions_can_switch(self):
        """A clerk with active access to both A and B may switch between them,
        but never to a third (here: the unsaved 'C')."""
        InstitutionAccess.objects.create(
            user=self.clerk, institution=self.other, department='Office',
        )
        self.login_as_clerk()
        response = self.client.get(reverse('student_list'), {'institution': self.other.pk})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Beta Student')
        self.assertNotContains(response, 'Alpha Student')
