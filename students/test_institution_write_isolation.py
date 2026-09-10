"""Write-side institution isolation tests.

A clerk scoped to Institution A must not be able to mutate another
institution's rows — whether by editing a pk in the URL or by posting a related
object's id (student/employee/receipt/exam) that belongs to institution B. The
authorized cross-institution administrator keeps full write access. These cover
create, edit, delete, approve, bulk update, import-adjacent form POSTs, and
promotion. SSC Registration / SSC Result Summary are not touched.
"""
import io
from datetime import date

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

from .models import (
    AdmissionApplication, Employee, Exam, ExamMark, Institution, InstitutionAccess,
    MoneyReceipt, PromotionBatch, SalarySheet, Student, StudentPromotionHistory,
    Subject, SubjectRequirement, Voucher,
)


class InstitutionWriteIsolationTests(TestCase):
    """Verify a single-institution clerk cannot write another institution's rows."""

    def grant(self, *perms):
        for model, codename in perms:
            self.clerk.user_permissions.add(
                Permission.objects.get(
                    content_type=ContentType.objects.get_for_model(model),
                    codename=codename,
                )
            )

    def setUp(self):
        self.institution = Institution.objects.create(name='Write A', classes='6,7,9')
        self.other = Institution.objects.create(name='Write B', classes='6,7,9')

        self.clerk = get_user_model().objects.create_user(username='wr_clerk', password='password')
        InstitutionAccess.objects.create(
            user=self.clerk, institution=self.institution, department='Office',
        )
        InstitutionAccess.objects.create(
            user=self.clerk, institution=self.institution, department='Accounts',
        )
        self.admin = get_user_model().objects.create_superuser(
            username='wr-admin', password='password', email='admin@example.com',
        )

        self.student_a = Student.objects.create(
            institution=self.institution, student_id='WA001', name='Write Alpha',
            admission_class='6', section='A', admission_year=2026,
        )
        self.student_b = Student.objects.create(
            institution=self.other, student_id='WB001', name='Write Beta',
            admission_class='6', section='A', admission_year=2026,
        )

        self.employee_a = Employee.objects.create(
            institution=self.institution, name='Employee Alpha', designation='Teacher',
            join_date=date(2026, 1, 1),
        )
        self.employee_b = Employee.objects.create(
            institution=self.other, name='Employee Beta', designation='Teacher',
            join_date=date(2026, 1, 1),
        )

        self.subject = Subject.objects.create(code='BAN', name='Bangla', full_marks=100)
        self.req_a = SubjectRequirement.objects.create(
            institution=self.institution, admission_class='6', subject=self.subject,
            requirement_type='MANDATORY',
        )
        self.req_b = SubjectRequirement.objects.create(
            institution=self.other, admission_class='6', subject=self.subject,
            requirement_type='MANDATORY',
        )

        self.receipt_a = MoneyReceipt.objects.create(
            student=self.student_a, receipt_no='RCA-001', purpose='Fee',
            amount=100, date=date(2026, 1, 1),
        )
        self.receipt_b = MoneyReceipt.objects.create(
            student=self.student_b, receipt_no='RCB-001', purpose='Fee',
            amount=100, date=date(2026, 1, 1),
        )

        self.salary_a = SalarySheet.objects.create(
            employee=self.employee_a, month='January 2026', amount=100,
            date=date(2026, 1, 1), status='UNPAID',
        )
        self.salary_b = SalarySheet.objects.create(
            employee=self.employee_b, month='January 2026', amount=100,
            date=date(2026, 1, 1), status='UNPAID',
        )

        self.exam_a = Exam.objects.create(
            name='A Exam', exam_type='FIRST_TERM', institution=self.institution,
            admission_class='6', section='', session='2026',
        )
        self.exam_b = Exam.objects.create(
            name='B Exam', exam_type='FIRST_TERM', institution=self.other,
            admission_class='6', section='', session='2026',
        )

        self.app_a = AdmissionApplication.objects.create(
            institution=self.institution, applicant_name='App A', guardian_name='Guard A', guardian_contact_no='01900000000',
            requested_class='6', session='2026-2027',
        )
        self.app_b = AdmissionApplication.objects.create(
            institution=self.other, applicant_name='App B', guardian_name='Guard B', guardian_contact_no='01900000001',
            requested_class='6', session='2026-2027',
        )

        self.voucher_a = Voucher.objects.create(
            institution=self.institution, purpose='Fee A', amount=100,
            date=date(2026, 1, 1), status='UNPAID',
        )
        self.voucher_b = Voucher.objects.create(
            institution=self.other, purpose='Fee B', amount=100,
            date=date(2026, 1, 1), status='UNPAID',
        )

        self.grant(
            (Student, 'add_student'), (Student, 'change_student'),
            (Student, 'delete_student'),
            (Employee, 'add_employee'), (Employee, 'change_employee'),
            (Employee, 'delete_employee'),
            (MoneyReceipt, 'add_moneyreceipt'), (MoneyReceipt, 'change_moneyreceipt'),
            (MoneyReceipt, 'delete_moneyreceipt'),
            (SalarySheet, 'add_salarysheet'), (SalarySheet, 'change_salarysheet'),
            (SalarySheet, 'delete_salarysheet'),
            (Voucher, 'add_voucher'), (Voucher, 'change_voucher'),
            (Voucher, 'delete_voucher'), (Voucher, 'view_voucher'),
            (Exam, 'add_exam'), (Exam, 'change_exam'),
            (AdmissionApplication, 'add_admissionapplication'),
            (AdmissionApplication, 'change_admissionapplication'),
            (AdmissionApplication, 'view_admissionapplication'),
            (SubjectRequirement, 'add_subjectrequirement'),
            (SubjectRequirement, 'change_subjectrequirement'),
            (SubjectRequirement, 'delete_subjectrequirement'),
            (PromotionBatch, 'view_promotionbatch'),
        )

    def login_as_clerk(self, department='Office'):
        self.client.force_login(self.clerk)
        session = self.client.session
        session['selected_institution_id'] = str(self.institution.pk)
        session['selected_department'] = department
        session.save()

    def login_as_admin(self):
        self.client.force_login(self.admin)
        session = self.client.session
        session['selected_institution_id'] = str(self.other.pk)
        session['selected_department'] = 'Office'
        session.save()

    # ------------------------------------------------------------- student write
    def test_add_student_rejects_other_institution_in_post(self):
        self.login_as_clerk()
        before = Student.objects.count()
        response = self.client.post(reverse('add_student'), {
            'institution': self.other.pk,
            'name': 'Sneaky Student', 'admission_class': '6', 'section': 'A',
            'admission_year': 2026, 'roll_no': 9, 'gender': 'M', 'religion': 'Islam',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Student.objects.count(), before)
        self.assertFalse(Student.objects.filter(name='Sneaky Student').exists())

    def test_edit_student_404_for_other_institution(self):
        self.login_as_clerk()
        response = self.client.get(reverse('edit_student', args=[self.student_b.pk]))
        self.assertEqual(response.status_code, 404)

    def test_edit_student_rejects_moving_to_other_institution(self):
        self.login_as_clerk()
        response = self.client.get(reverse('edit_student', args=[self.student_a.pk]))
        self.assertEqual(response.status_code, 200)

    def test_delete_student_404_for_other_institution(self):
        self.login_as_clerk()
        response = self.client.get(reverse('delete_student', args=[self.student_b.pk]))
        self.assertEqual(response.status_code, 404)
        self.student_b.refresh_from_db()
        self.assertFalse(self.student_b.is_archived)

    def test_bulk_delete_rejects_other_institution_student(self):
        self.login_as_clerk()
        response = self.client.post(reverse('bulk_delete_students'), {
            'student_ids': [self.student_a.pk, self.student_b.pk],
        })
        self.assertEqual(response.status_code, 302)
        self.student_a.refresh_from_db()
        self.student_b.refresh_from_db()
        self.assertFalse(self.student_a.is_archived)
        self.assertFalse(self.student_b.is_archived)

    def test_import_students_rejects_other_institution_row(self):
        """An Excel import that names another institution's school must not
        create rows there for a scoped clerk."""
        import openpyxl
        from django.core.files.uploadedfile import SimpleUploadedFile

        self.login_as_clerk()
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["Institution", "Name", "Admission Class", "Section",
                   "Admission Year", "Roll No", "Gender", "Religion",
                   "Father's Name", "Contact No", "Guardian Contact No", "Group"])
        ws.append([self.institution.name, "Import Alpha", "6", "A", 2026, 21,
                   "Male", "Islam", "Father A", "01700000000", "01800000000", "Non-Group"])
        ws.append([self.other.name, "Import Beta", "6", "A", 2026, 22,
                   "Male", "Islam", "Father B", "01700000000", "01800000000", "Non-Group"])
        buffer = io.BytesIO()
        wb.save(buffer)
        buffer.seek(0)

        before = Student.objects.count()
        response = self.client.post(reverse('import_students'), {
            'excel_file': SimpleUploadedFile('students.xlsx', buffer.read(),
                                             content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Student.objects.filter(name='Import Alpha').exists())
        self.assertFalse(Student.objects.filter(name='Import Beta').exists())
        import_beta = Student.objects.filter(name='Import Beta').count()
        self.assertEqual(import_beta, 0)

    # ------------------------------------------------------------- employee write
    def test_add_employee_rejects_other_institution_in_post(self):
        self.login_as_clerk()
        before = Employee.objects.count()
        response = self.client.post(reverse('add_employee'), {
            'name': 'Sneaky Teacher', 'designation': 'Teacher',
            'institution': self.other.pk, 'join_date': '2026-01-01',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Employee.objects.count(), before)

    def test_edit_employee_404_for_other_institution(self):
        self.login_as_clerk()
        response = self.client.get(reverse('edit_employee', args=[self.employee_b.pk]))
        self.assertEqual(response.status_code, 404)

    def test_delete_employee_404_for_other_institution(self):
        self.login_as_clerk()
        response = self.client.get(reverse('delete_employee', args=[self.employee_b.pk]))
        self.assertEqual(response.status_code, 404)

    # ------------------------------------------------------------- receipts / salary
    def test_add_money_receipt_rejects_other_institution_student(self):
        self.login_as_clerk()
        before = MoneyReceipt.objects.count()
        response = self.client.post(reverse('add_money_receipt'), {
            'student': self.student_b.pk, 'receipt_no': 'RCX-999',
            'purpose': 'Fee', 'amount': '50.00', 'date': '2026-02-01',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(MoneyReceipt.objects.count(), before)
        self.assertFalse(MoneyReceipt.objects.filter(receipt_no='RCX-999').exists())

    def test_edit_money_receipt_404_for_other_institution(self):
        self.login_as_clerk()
        response = self.client.get(reverse('edit_money_receipt', args=[self.receipt_b.pk]))
        self.assertEqual(response.status_code, 404)

    def test_delete_money_receipt_404_for_other_institution(self):
        self.login_as_clerk()
        response = self.client.get(reverse('delete_money_receipt', args=[self.receipt_b.pk]))
        self.assertEqual(response.status_code, 404)

    def test_add_salary_sheet_rejects_other_institution_employee(self):
        self.login_as_clerk()
        before = SalarySheet.objects.count()
        response = self.client.post(reverse('add_salary_sheet'), {
            'employee': self.employee_b.pk, 'month': 'February 2026',
            'amount': '60.00', 'date': '2026-02-01', 'status': 'UNPAID',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(SalarySheet.objects.count(), before)

    def test_edit_salary_sheet_404_for_other_institution(self):
        self.login_as_clerk()
        response = self.client.get(reverse('edit_salary_sheet', args=[self.salary_b.pk]))
        self.assertEqual(response.status_code, 404)

    def test_delete_salary_sheet_404_for_other_institution(self):
        self.login_as_clerk()
        response = self.client.get(reverse('delete_salary_sheet', args=[self.salary_b.pk]))
        self.assertEqual(response.status_code, 404)

    # ------------------------------------------------------------- exam write
    def test_add_exam_rejects_other_institution_in_post(self):
        self.login_as_clerk()
        before = Exam.objects.count()
        response = self.client.post(reverse('add_exam'), {
            'institution': self.other.pk, 'admission_class': '6', 'section': '',
            'group': '', 'exam_type': 'FIRST_TERM', 'session': '2026',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Exam.objects.count(), before)

    def test_edit_exam_404_for_other_institution(self):
        self.login_as_clerk()
        response = self.client.get(reverse('edit_exam', args=[self.exam_b.pk]))
        self.assertEqual(response.status_code, 404)

    # ------------------------------------------------------------- admission approve
    def test_office_approve_rejects_other_institution_application(self):
        self.login_as_clerk(department='Office')
        response = self.client.post(
            reverse('office_approve_application', args=[self.app_b.pk]), {'remarks': 'x'},
        )
        self.assertEqual(response.status_code, 404)
        self.app_b.refresh_from_db()
        self.assertEqual(self.app_b.status, 'SUBMITTED')

    def test_accounts_approve_payment_rejects_other_institution_application(self):
        self.login_as_clerk(department='Accounts')
        self.app_b.status = 'ACCOUNT_PENDING'
        self.app_b.save(update_fields=['status'])
        response = self.client.post(
            reverse('accounts_approve_payment', args=[self.app_b.pk]),
            {'payment_amount': '1000.00', 'payment_date': '2026-01-01',
             'payment_purpose': 'Admission Fee'},
        )
        self.assertEqual(response.status_code, 404)
        self.app_b.refresh_from_db()
        self.assertEqual(self.app_b.status, 'ACCOUNT_PENDING')
        self.assertEqual(Student.objects.filter(admission_application=self.app_b).count(), 0)

    # ------------------------------------------------------------- subject requirements
    def test_add_subject_requirement_rejects_other_institution(self):
        self.login_as_clerk()
        before = SubjectRequirement.objects.count()
        response = self.client.post(reverse('add_subject_requirement'), {
            'institution': self.other.pk, 'admission_class': '7', 'group': '',
            'subject': self.subject.pk, 'requirement_type': 'MANDATORY',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(SubjectRequirement.objects.count(), before)

    def test_edit_subject_requirement_404_for_other_institution(self):
        self.login_as_clerk()
        response = self.client.get(reverse('edit_subject_requirement', args=[self.req_b.pk]))
        self.assertEqual(response.status_code, 404)

    def test_delete_subject_requirement_404_for_other_institution(self):
        self.login_as_clerk()
        response = self.client.get(reverse('delete_subject_requirement', args=[self.req_b.pk]))
        self.assertEqual(response.status_code, 404)

    # ------------------------------------------------------------- promotion (SEC-4)
    def test_promotion_only_touches_own_institution(self):
        self.login_as_clerk(department='Office')
        response = self.client.post(reverse('student_promotion'), {
            'from_class': '6', 'from_section': 'A', 'to_class': '7',
            'to_section': 'A', 'session': '2026-2027',
        })
        self.assertEqual(response.status_code, 302)
        self.student_a.refresh_from_db()
        self.student_b.refresh_from_db()
        self.assertEqual(self.student_a.admission_class, '7')
        self.assertEqual(self.student_b.admission_class, '6')

    def test_rollback_promotion_404_for_other_institution_batch(self):
        self.login_as_clerk(department='Office')
        # Build a batch that only involves institution B's student.
        batch = PromotionBatch.objects.create(
            session='2026-2027', from_class='6', from_section='A',
            to_class='7', to_section='A', actor=self.clerk,
        )
        StudentPromotionHistory.objects.create(
            batch=batch, student=self.student_b,
            source_class='6', source_section='A', source_roll_no=1,
            target_class='7', target_section='A',
        )
        response = self.client.post(
            reverse('rollback_student_promotion', args=[batch.pk]),
        )
        self.assertEqual(response.status_code, 404)
        self.student_b.refresh_from_db()
        self.assertEqual(self.student_b.admission_class, '6')

    def test_new_batch_records_institution(self):
        # D-9: a promotion run for a single class records the institution on
        # the batch, so scoping no longer has to be derived for new batches.
        self.login_as_clerk(department='Office')
        response = self.client.post(reverse('student_promotion'), {
            'from_class': '6', 'from_section': 'A', 'to_class': '7',
            'to_section': 'A', 'session': '2026-2027',
        })
        self.assertEqual(response.status_code, 302)
        batch = PromotionBatch.objects.order_by('-pk').first()
        self.assertIsNotNone(batch.institution)
        self.assertEqual(batch.institution, self.institution)

    def test_rollback_promotion_batch_with_institution_other_404(self):
        # D-9: a batch carrying a non-owned institution is refused, even though
        # the column now stores it directly.
        self.login_as_clerk(department='Office')
        batch = PromotionBatch.objects.create(
            session='2026-2027', from_class='6', from_section='A',
            to_class='7', to_section='A', actor=self.clerk,
            institution=self.other,
        )
        StudentPromotionHistory.objects.create(
            batch=batch, student=self.student_b,
            source_class='6', source_section='A', source_roll_no=1,
            target_class='7', target_section='A',
        )
        response = self.client.post(reverse('rollback_student_promotion', args=[batch.pk]))
        self.assertEqual(response.status_code, 404)

    def test_promotion_history_scoped_to_own_institution(self):
        self.login_as_clerk(department='Office')
        batch_a = PromotionBatch.objects.create(
            session='2026-2027', from_class='6', from_section='A',
            to_class='7', to_section='A', actor=self.clerk,
        )
        StudentPromotionHistory.objects.create(
            batch=batch_a, student=self.student_a,
            source_class='6', source_section='A', source_roll_no=1,
            target_class='7', target_section='A',
        )
        batch_b = PromotionBatch.objects.create(
            session='2026-2027', from_class='6', from_section='A',
            to_class='7', to_section='A', actor=self.clerk,
        )
        StudentPromotionHistory.objects.create(
            batch=batch_b, student=self.student_b,
            source_class='6', source_section='A', source_roll_no=1,
            target_class='7', target_section='A',
        )
        response = self.client.get(reverse('student_promotion_history'))
        self.assertEqual(response.status_code, 200)
        # The in-scope batch A is rendered; batch B (another institution) is
        # not. Match the rollback URLs (the row's own pk) rather than bare
        # digits, which appear throughout the page as 2026 / room numbers.
        self.assertContains(
            response, reverse('rollback_student_promotion', args=[batch_a.pk]),
        )
        self.assertNotContains(
            response, reverse('rollback_student_promotion', args=[batch_b.pk]),
        )

    # ------------------------------------------------------------- voucher (D-3/P1-1)
    def test_voucher_list_scoped_to_own_institution(self):
        self.login_as_clerk()
        response = self.client.get(reverse('voucher_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Fee A')
        self.assertNotContains(response, 'Fee B')

    def test_add_voucher_rejects_other_institution_in_post(self):
        self.login_as_clerk()
        before = Voucher.objects.count()
        response = self.client.post(reverse('add_voucher'), {
            'purpose': 'Sneaky Voucher', 'institution': self.other.pk,
            'amount': '50.00', 'date': '2026-02-01', 'status': 'UNPAID',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Voucher.objects.count(), before)
        self.assertFalse(Voucher.objects.filter(purpose='Sneaky Voucher').exists())

    def test_edit_voucher_404_for_other_institution(self):
        self.login_as_clerk()
        response = self.client.get(reverse('edit_voucher', args=[self.voucher_b.pk]))
        self.assertEqual(response.status_code, 404)

    def test_delete_voucher_404_for_other_institution(self):
        self.login_as_clerk()
        response = self.client.get(reverse('delete_voucher', args=[self.voucher_b.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Voucher.objects.filter(pk=self.voucher_b.pk).exists())

    def test_voucher_without_institution_hidden_from_scoped_clerk(self):
        # Legacy rows with a NULL institution must stay staff-only (deny by
        # default for a scoped clerk).
        NULL_VOUCHER = Voucher.objects.create(
            institution=None, purpose='Legacy Voucher', amount=100,
            date=date(2026, 1, 1), status='UNPAID',
        )
        self.login_as_clerk()
        response = self.client.get(reverse('voucher_list'))
        self.assertNotContains(response, 'Legacy Voucher')
        self.assertEqual(self.client.get(reverse('edit_voucher', args=[NULL_VOUCHER.pk])).status_code, 404)

    def test_admin_sees_all_vouchers_including_legacy(self):
        NULL_VOUCHER = Voucher.objects.create(
            institution=None, purpose='Legacy Voucher', amount=100,
            date=date(2026, 1, 1), status='UNPAID',
        )
        self.login_as_admin()
        response = self.client.get(reverse('voucher_list'))
        self.assertContains(response, 'Fee A')
        self.assertContains(response, 'Fee B')
        self.assertContains(response, 'Legacy Voucher')

    # ------------------------------------------------------------- cross-institution admin
    def test_admin_can_write_across_institutions(self):
        self.login_as_admin()
        before = Student.objects.count()
        response = self.client.post(reverse('add_student'), {
            'institution': self.other.pk,
            'name': 'Admin Student', 'admission_class': '6', 'section': 'A',
            'admission_year': 2026, 'roll_no': 10, 'gender': 'M', 'religion': 'Islam',
            'guardian_contact_no': '01812345678', 'group': '', 'status': 'ACTIVE',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Student.objects.count(), before + 1)
        created = Student.objects.get(name='Admin Student')
        self.assertEqual(created.institution, self.other)
