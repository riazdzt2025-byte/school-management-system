from django.test import TestCase

from io import BytesIO
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
try:
	from openpyxl import Workbook
except ModuleNotFoundError:
	Workbook = None

from .models import (
	AdmissionApplication, AuditLog, Exam, ExamMark, Institution, MoneyReceipt,
	PromotionBatch, Student, Subject,
)


class PromotionAndAuditTests(TestCase):
	def setUp(self):
		self.institution = Institution.objects.create(name='Promotion School', classes='6,7,8')
		self.user = get_user_model().objects.create_superuser(username='promotion-admin', password='password')
		self.client.force_login(self.user)
		self.student = Student.objects.create(institution=self.institution, student_id='P001', name='Promoted One', admission_class='6', section='A', admission_year=2026)
		self.untouched = Student.objects.create(institution=self.institution, student_id='P002', name='Promoted Two', admission_class='6', section='A', admission_year=2026)

	def test_promotion_requires_session_and_records_history(self):
		response = self.client.post(reverse('student_promotion'), {
			'from_class': '6', 'from_section': 'A', 'to_class': '7', 'to_section': 'B', 'session': '2026-2027',
		})
		self.assertRedirects(response, reverse('student_list'))
		batch = PromotionBatch.objects.get()
		self.assertEqual(batch.session, '2026-2027')
		self.assertEqual(batch.student_history.count(), 2)
		self.assertTrue(AuditLog.objects.filter(action='students_promoted', object_id=str(batch.pk)).exists())

	def test_rollback_only_restores_students_still_at_target(self):
		self.client.post(reverse('student_promotion'), {
			'from_class': '6', 'from_section': 'A', 'to_class': '7', 'to_section': 'B', 'session': '2026-2027',
		})
		self.student.admission_class = '8'
		self.student.save(update_fields=['admission_class'])
		batch = PromotionBatch.objects.get()
		response = self.client.post(reverse('rollback_student_promotion', args=[batch.pk]))
		self.assertRedirects(response, reverse('student_promotion_history'))
		self.student.refresh_from_db()
		self.untouched.refresh_from_db()
		self.assertEqual(self.student.admission_class, '8')
		self.assertEqual(self.untouched.admission_class, '6')
		self.assertEqual(batch.student_history.filter(rolled_back_at__isnull=False).count(), 1)
		self.assertTrue(AuditLog.objects.filter(action='students_promotion_rollback').exists())

	def test_promotion_rejects_same_location(self):
		response = self.client.post(reverse('student_promotion'), {
			'from_class': '6', 'from_section': 'A', 'to_class': '6', 'to_section': 'a', 'session': '2026-2027',
		})
		self.assertEqual(response.status_code, 200)
		self.assertEqual(PromotionBatch.objects.count(), 0)


class ExamWorkflowTests(TestCase):
	def setUp(self):
		self.institution = Institution.objects.create(name='Test School', classes='6')
		self.student = Student.objects.create(
			institution=self.institution, student_id='S001', name='Student One',
			admission_class='6', section='A', admission_year=2026,
		)
		self.other_student = Student.objects.create(
			institution=self.institution, student_id='S002', name='Student Two',
			admission_class='7', section='A', admission_year=2026,
		)
		self.subject = Subject.objects.create(code='ENG', name='English', full_marks=100)
		self.exam = Exam.objects.create(
			name='Mid Term', exam_type='MID_TERM', institution=self.institution,
			admission_class='6', section='A', session='2026',
		)
		user = get_user_model().objects.create_user(username='exam-user', password='password')
		exammark_content_type = ContentType.objects.get_for_model(ExamMark)
		exam_content_type = ContentType.objects.get_for_model(Exam)
		user.user_permissions.add(
			Permission.objects.get(content_type=exammark_content_type, codename='add_exammark'),
			Permission.objects.get(content_type=exam_content_type, codename='change_exam'),
		)
		self.client.force_login(user)

	def workbook_upload(self, rows):
		workbook = Workbook()
		sheet = workbook.active
		sheet.append(['Student ID', 'Subject Code', 'Marks'])
		for row in rows:
			sheet.append(row)
		output = BytesIO()
		workbook.save(output)
		return SimpleUploadedFile(
			'marks.xlsx', output.getvalue(),
			content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
		)

	def test_unpublished_result_views_redirect_to_exam_list(self):
		urls = [
			reverse('result_sheet', args=[self.exam.pk]),
			reverse('exam_result_summary', args=[self.exam.pk]),
			reverse('top_10', args=[self.exam.pk]),
			reverse('student_result_detail', args=[self.exam.pk, self.student.pk]),
			reverse('result_card', args=[self.exam.pk, self.student.pk]),
		]
		for url in urls:
			with self.subTest(url=url):
				response = self.client.get(url)
				self.assertRedirects(response, reverse('exam_list'))

	def test_publish_toggle_only_mutates_on_post(self):
		url = reverse('toggle_publish_exam', args=[self.exam.pk])
		response = self.client.get(url)
		self.assertEqual(response.status_code, 405)
		self.exam.refresh_from_db()
		self.assertFalse(self.exam.is_published)

		response = self.client.post(url)
		self.assertRedirects(response, reverse('exam_list'))
		self.exam.refresh_from_db()
		self.assertTrue(self.exam.is_published)

	@skipUnless(Workbook, 'openpyxl is required for Excel import tests')
	def test_import_exam_marks_success(self):
		response = self.client.post(
			reverse('import_exam_marks', args=[self.exam.pk]),
			{'excel_file': self.workbook_upload([['S001', 'ENG', 87.5]])},
		)
		self.assertRedirects(response, reverse('exam_list'))
		mark = ExamMark.objects.get(exam=self.exam, student=self.student, subject=self.subject)
		self.assertEqual(str(mark.marks_obtained), '87.50')

	@skipUnless(Workbook, 'openpyxl is required for Excel import tests')
	def test_invalid_row_rejects_entire_import(self):
		response = self.client.post(
			reverse('import_exam_marks', args=[self.exam.pk]),
			{'excel_file': self.workbook_upload([
				['S001', 'ENG', 75],
				['S002', 'ENG', 80],
			])},
		)
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'not a member of this exam class/section')
		self.assertEqual(ExamMark.objects.filter(exam=self.exam).count(), 0)



class AdmissionApplicationWorkflowTests(TestCase):
	def setUp(self):
		self.institution = Institution.objects.create(name='Admission School', classes='6,7')
		self.user = get_user_model().objects.create_superuser(
			username='admission-admin', password='password', email='admin@example.com'
		)
		self.client.force_login(self.user)
		self.application = AdmissionApplication.objects.create(
			institution=self.institution, applicant_name='Applicant One',
			applicant_contact_no='01800000000', guardian_name='Guardian One',
			guardian_contact_no='01900000000', requested_class='6',
			requested_section='A', session='2026-2027',
		)

	def post_transition(self, name, data=None):
		return self.client.post(reverse(name, args=[self.application.pk]), data or {})

	def test_office_transition_requires_post_and_handoff(self):
		url = reverse('office_approve_application', args=[self.application.pk])
		self.assertEqual(self.client.get(url).status_code, 405)
		self.post_transition('office_approve_application', {'remarks': 'Verified'})
		self.application.refresh_from_db()
		self.assertEqual(self.application.status, 'OFFICE_APPROVED')
		self.post_transition('office_handoff_application')
		self.application.refresh_from_db()
		self.assertEqual(self.application.status, 'ACCOUNT_PENDING')

	def test_invalid_transition_does_not_mutate(self):
		self.post_transition('office_handoff_application')
		self.application.refresh_from_db()
		self.assertEqual(self.application.status, 'SUBMITTED')
		self.assertEqual(Student.objects.count(), 0)

	def test_accounts_queue_filters_by_requested_class(self):
		self.application.status = 'ACCOUNT_PENDING'
		self.application.save(update_fields=['status'])
		other = AdmissionApplication.objects.create(
			institution=self.institution, applicant_name='Applicant Two',
			applicant_contact_no='01800000001', guardian_name='Guardian Two',
			guardian_contact_no='01900000001', requested_class='7', session='2026-2027',
			status='ACCOUNT_PENDING',
		)
		response = self.client.get(reverse('accounts_admission_queue'), {'admission_class': '6'})
		self.assertContains(response, self.application.application_number)
		self.assertNotContains(response, other.application_number)

	def test_payment_approval_creates_one_student_and_receipt(self):
		self.application.status = 'ACCOUNT_PENDING'
		self.application.save(update_fields=['status'])
		data = {
			'payment_amount': '1500.00', 'payment_date': '2026-08-27',
			'payment_purpose': 'Admission Fee', 'account_remarks': 'Paid',
		}
		response = self.post_transition('accounts_approve_payment', data)
		self.assertRedirects(response, reverse('admission_application_detail', args=[self.application.pk]))
		self.application.refresh_from_db()
		self.assertEqual(self.application.status, 'ENROLLED')
		self.assertIsNotNone(self.application.enrolled_student_id)
		self.assertEqual(Student.objects.filter(admission_application=self.application).count(), 1)
		self.assertEqual(MoneyReceipt.objects.filter(student=self.application.enrolled_student).count(), 1)
		self.assertEqual(MoneyReceipt.objects.filter(student=self.application.enrolled_student).first().created_by, self.user)
		self.assertEqual(self.post_transition('accounts_approve_payment', data).status_code, 302)
		self.assertEqual(Student.objects.filter(admission_application=self.application).count(), 1)
		self.assertEqual(MoneyReceipt.objects.filter(student=self.application.enrolled_student).count(), 1)

# Create your tests here.
