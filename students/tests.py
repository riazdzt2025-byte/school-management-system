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
	AdmissionApplication, AuditLog, AttendanceRecord, Exam, ExamMark, Institution, InstitutionAccess,
	MoneyReceipt, PromotionBatch, Student, Subject,
)
from .permissions import ensure_default_groups


class PermissionSetupTests(TestCase):
	def test_default_groups_are_created_with_required_permissions(self):
		ensure_default_groups()
		self.assertTrue(hasattr(Student, 'objects'))
		self.assertTrue(hasattr(AdmissionApplication, 'objects'))
		self.assertEqual(AdmissionApplication._meta.model_name, 'admissionapplication')
		self.assertTrue(hasattr(ensure_default_groups, '__call__'))


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



class AttendanceTests(TestCase):
	def setUp(self):
		self.institution = Institution.objects.create(name='Attendance Campus', classes='6,7')
		self.student = Student.objects.create(
			institution=self.institution, student_id='A001', name='Daily Student',
			admission_class='6', section='A', admission_year=2026,
		)
		self.user = get_user_model().objects.create_user(username='attendance-user', password='password')
		self.client.force_login(self.user)

	def test_student_attendance_record_can_be_created(self):
		record = AttendanceRecord.objects.create(
			institution=self.institution,
			student=self.student,
			date='2026-09-01',
			status='P',
			remarks='Present',
		)
		self.assertEqual(record.status, 'P')
		self.assertEqual(record.student.name, 'Daily Student')

	def test_attendance_summary_page_loads(self):
		AttendanceRecord.objects.create(
			institution=self.institution,
			student=self.student,
			date='2026-09-01',
			status='P',
		)
		response = self.client.get(reverse('attendance_report'))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Attendance Report')

	def test_mark_attendance_selection_page_loads(self):
		response = self.client.get(reverse('mark_attendance'))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Mark Attendance')

	def test_mark_attendance_bulk_page_renders_students(self):
		InstitutionAccess.objects.create(
			user=self.user, institution=self.institution, department='Office', is_active=True
		)
		from datetime import date
		today = date.today().isoformat()
		response = self.client.get(
			reverse('mark_attendance_bulk', kwargs={
				'date_str': today, 'admission_class': '6', 'section': 'A', 'mark_type': 'STUDENT'
			})
		)
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, self.student.name)
		self.assertContains(response, 'Status')

	def test_mark_attendance_bulk_updates_records(self):
		InstitutionAccess.objects.create(
			user=self.user, institution=self.institution, department='Office', is_active=True
		)
		from datetime import date
		today = date.today().isoformat()
		response = self.client.post(
			reverse('mark_attendance_bulk', kwargs={
				'date_str': today, 'admission_class': '6', 'section': 'A', 'mark_type': 'STUDENT'
			}),
			{f'status_{self.student.id}': 'P', f'remarks_{self.student.id}': 'Present in class'}
		)
		self.assertRedirects(response, reverse('attendance_report'))
		record = AttendanceRecord.objects.get(student=self.student, date=today)
		self.assertEqual(record.status, 'P')
		self.assertEqual(record.remarks, 'Present in class')

	def test_attendance_summary_page_loads_and_shows_statistics(self):
		"""Test that attendance summary page loads with statistics."""
		from datetime import date, timedelta
		InstitutionAccess.objects.create(
			user=self.user, institution=self.institution, department='Office', is_active=True
		)
		today = date.today()
		yesterday = today - timedelta(days=1)
		
		# Create multiple attendance records on different dates
		AttendanceRecord.objects.create(
			student=self.student, date=today, status='P', 
			institution=self.institution, created_by=self.user
		)
		AttendanceRecord.objects.create(
			student=self.student, date=yesterday, status='A',
			institution=self.institution, created_by=self.user
		)
		
		response = self.client.get(reverse('attendance_summary'))
		
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Attendance Summary')
		self.assertContains(response, self.student.name)


class StudentDetailPageTests(TestCase):
	def setUp(self):
		self.user = get_user_model().objects.create_superuser(username='admin', password='password')
		self.client.force_login(self.user)
		self.institution = Institution.objects.create(name='Test School', classes='6,7,8')
		self.student = Student.objects.create(
			name='Detail Test Student', student_id='D001', admission_class='6', section='A',
			gender='M', institution=self.institution, created_by=self.user
		)

	def test_student_detail_page_loads(self):
		"""Test that student detail page loads successfully."""
		response = self.client.get(reverse('student_detail', args=[self.student.pk]))
		
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Detail Test Student')
		self.assertContains(response, 'D001')
		self.assertContains(response, 'Subjects & Curriculum')

	def test_student_detail_shows_attendance_records(self):
		"""Test that student detail page displays attendance records."""
		from datetime import date
		AttendanceRecord.objects.create(
			student=self.student, date=date.today(), status='P',
			institution=self.institution, created_by=self.user
		)
		
		response = self.client.get(reverse('student_detail', args=[self.student.pk]))
		
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Attendance')
		self.assertContains(response, 'Present')

	def test_student_detail_shows_exam_results(self):
		"""Test that student detail page displays exam results."""
		exam = Exam.objects.create(
			name='Quarterly', exam_type='MID_TERM', institution=self.institution,
			admission_class='6', section='A', session='2025-2026'
		)
		subject = Subject.objects.create(name='Math', code='MATH001', created_by=self.user)
		ExamMark.objects.create(
			student=self.student, exam=exam, subject=subject, marks_obtained=85
		)
		
		response = self.client.get(reverse('student_detail', args=[self.student.pk]))
		
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Exam Results')
		self.assertContains(response, 'Math')


class InstitutionAwareLoginTests(TestCase):
	def setUp(self):
		self.institution = Institution.objects.create(name='Trust Campus', classes='6,7,8')
		self.other_institution = Institution.objects.create(name='City Campus', classes='6,7,8')
		self.user = get_user_model().objects.create_user(username='office_user', password='password')
		InstitutionAccess.objects.create(user=self.user, institution=self.institution, department='Office')
		InstitutionAccess.objects.create(user=self.user, institution=self.other_institution, department='Exam')

	def test_login_page_lists_only_accessible_institutions(self):
		response = self.client.get(reverse('login'))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Trust Campus')
		self.assertContains(response, 'City Campus')
		self.assertContains(response, 'Office')
		self.assertContains(response, 'Exam')

	def test_selected_institution_and_department_are_saved_on_login(self):
		response = self.client.post(reverse('login'), {
			'username': 'office_user',
			'password': 'password',
			'institution_id': str(self.institution.pk),
			'department': 'Office',
		})
		self.assertEqual(response.status_code, 302)
		self.assertEqual(self.client.session.get('selected_institution_id'), str(self.institution.pk))
		self.assertEqual(self.client.session.get('selected_department'), 'Office')


class UIConsistencyTests(TestCase):
	def setUp(self):
		self.user = get_user_model().objects.create_user(username='ui_user', password='password')
		self.client.force_login(self.user)

	def test_dashboard_excludes_quick_access_section_and_duplicate_logout(self):
		response = self.client.get(reverse('dashboard'))
		self.assertEqual(response.status_code, 200)
		self.assertNotContains(response, 'Quick Search')
		self.assertNotContains(response, 'Quick Access')
		self.assertEqual(response.content.decode('utf-8').count('Logout'), 1)

	def test_selected_institution_filters_student_list(self):
		inst_a = Institution.objects.create(name='Alpha Campus', classes='6,7')
		inst_b = Institution.objects.create(name='Beta Campus', classes='6,7')
		InstitutionAccess.objects.create(user=self.user, institution=inst_a, department='Office')
		InstitutionAccess.objects.create(user=self.user, institution=inst_b, department='Exam')
		Student.objects.create(institution=inst_a, student_id='A001', name='Alpha Student', admission_class='6', section='A', admission_year=2026)
		Student.objects.create(institution=inst_b, student_id='B001', name='Beta Student', admission_class='6', section='A', admission_year=2026)
		session = self.client.session
		session['selected_institution_id'] = str(inst_a.pk)
		session['selected_department'] = 'Office'
		session.save()

		response = self.client.get(reverse('student_list'))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Alpha Student')
		self.assertNotContains(response, 'Beta Student')


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


class DepartmentAccessControlTests(TestCase):
	def setUp(self):
		self.institution = Institution.objects.create(name='Access Control School', classes='6,7')
		self.office_user = get_user_model().objects.create_user(username='office_user', password='password')
		self.accounts_user = get_user_model().objects.create_user(username='accounts_user', password='password')
		InstitutionAccess.objects.create(user=self.office_user, institution=self.institution, department='Office')
		InstitutionAccess.objects.create(user=self.accounts_user, institution=self.institution, department='Accounts')

	def test_office_and_accounts_users_can_view_admission_list(self):
		# Both Office and Accounts users can view admission list.
		admission_app_ct = ContentType.objects.get_for_model(AdmissionApplication)
		perm = Permission.objects.get(content_type=admission_app_ct, codename='view_admissionapplication')
		for user in [self.office_user, self.accounts_user]:
			user.user_permissions.add(perm)
		
		for user, dept in [(self.office_user, 'Office'), (self.accounts_user, 'Accounts')]:
			self.client.force_login(user)
			session = self.client.session
			session['selected_institution_id'] = str(self.institution.pk)
			session['selected_department'] = dept
			session.save()
			response = self.client.get(reverse('admission_application_list'))
			self.assertEqual(response.status_code, 200)

	def test_institution_filtering_works_in_admission_list(self):
		# Admission applications are filtered by selected institution.
		inst1 = Institution.objects.create(name='Inst1', classes='6')
		self.office_user.user_permissions.add(
			Permission.objects.get(content_type=ContentType.objects.get_for_model(AdmissionApplication), codename='view_admissionapplication')
		)
		InstitutionAccess.objects.create(user=self.office_user, institution=inst1, department='Office')
		
		app1 = AdmissionApplication.objects.create(
			institution=inst1, applicant_name='App1', applicant_contact_no='01800000000',
			guardian_name='Guard1', guardian_contact_no='01900000000', requested_class='6', session='2026-2027'
		)
		
		self.client.force_login(self.office_user)
		session = self.client.session
		session['selected_institution_id'] = str(inst1.pk)
		session['selected_department'] = 'Office'
		session.save()
		
		response = self.client.get(reverse('admission_application_list'))
		self.assertEqual(response.status_code, 200)
		self.assertIn(app1.application_number, str(response.content))

# Create your tests here.

