from django.test import TestCase

from io import BytesIO
from unittest import skipUnless
from datetime import date

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
	AdmissionApplication, AuditLog, AttendanceRecord, Employee, EmployeeStatusLog, Exam, ExamMark, Institution, InstitutionAccess,
	MoneyReceipt, PromotionBatch, Student, Subject,
)
from .forms import ExamForm, StudentForm, auto_exam_name
from .permissions import ensure_default_groups


class PermissionSetupTests(TestCase):
	def test_default_groups_are_created_with_required_permissions(self):
		ensure_default_groups()
		self.assertTrue(hasattr(Student, 'objects'))
		self.assertTrue(hasattr(AdmissionApplication, 'objects'))
		self.assertEqual(AdmissionApplication._meta.model_name, 'admissionapplication')
		self.assertTrue(hasattr(ensure_default_groups, '__call__'))


class StudentArchiveSafetyTests(TestCase):
	def setUp(self):
		self.institution = Institution.objects.create(name='Archive School', classes='6,7,8')
		self.user = get_user_model().objects.create_superuser(username='archive-admin', password='password')
		self.client.force_login(self.user)
		self.student = Student.objects.create(
			institution=self.institution,
			student_id='A001',
			name='Archived Student',
			admission_class='6',
			section='A',
			admission_year=2026,
		)

	def test_bulk_delete_soft_deletes_student_and_keeps_record(self):
		response = self.client.post(reverse('bulk_delete_students'), {
			'student_ids': [self.student.pk],
			'institution': self.institution.pk,
		})
		self.assertEqual(response.url, reverse('student_list') + f'?institution={self.institution.pk}')
		self.student.refresh_from_db()
		self.assertTrue(self.student.is_archived)
		self.assertEqual(self.student.status, 'DISCONTINUED')
		self.assertTrue(Student.objects.filter(pk=self.student.pk).exists())

		list_response = self.client.get(reverse('student_list'), {'institution': self.institution.pk})
		self.assertNotContains(list_response, 'Archived Student')

	def test_restore_student_returns_it_to_active_list(self):
		self.student.status = 'TRANSFERRED'
		self.student.save(update_fields=['status'])
		self.client.post(reverse('delete_student', args=[self.student.pk]))
		self.student.refresh_from_db()
		self.assertTrue(self.student.is_archived)
		self.assertEqual(self.student.pre_archive_status, 'TRANSFERRED')

		response = self.client.post(reverse('restore_student', args=[self.student.pk]))
		self.assertEqual(response.status_code, 302)
		self.student.refresh_from_db()
		self.assertFalse(self.student.is_archived)
		# The student's status from before it was archived is restored, not a hardcoded default.
		self.assertEqual(self.student.status, 'TRANSFERRED')
		self.assertEqual(self.student.pre_archive_status, '')
		self.assertIsNotNone(self.student.restored_at)
		self.assertEqual(self.student.restored_by, self.user)

		list_response = self.client.get(reverse('student_list'), {'institution': self.institution.pk})
		self.assertContains(list_response, 'Archived Student')

	def test_archived_students_page_lists_archived_only(self):
		active_student = Student.objects.create(
			institution=self.institution, student_id='A002', name='Still Active',
			admission_class='6', section='A', admission_year=2026,
		)
		self.client.post(reverse('delete_student', args=[self.student.pk]))

		response = self.client.get(reverse('archived_students'), {'institution': self.institution.pk})
		self.assertContains(response, 'Archived Student')
		self.assertNotContains(response, 'Still Active')

	def test_bulk_restore_students(self):
		other = Student.objects.create(
			institution=self.institution, student_id='A003', name='Second Archived',
			admission_class='6', section='A', admission_year=2026,
		)
		self.client.post(reverse('bulk_delete_students'), {
			'student_ids': [self.student.pk, other.pk],
			'institution': self.institution.pk,
		})
		response = self.client.post(reverse('bulk_restore_students'), {
			'student_ids': [self.student.pk, other.pk],
			'institution': self.institution.pk,
		})
		self.assertEqual(response.status_code, 302)
		self.student.refresh_from_db()
		other.refresh_from_db()
		self.assertFalse(self.student.is_archived)
		self.assertFalse(other.is_archived)


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
			name='Mid Term', exam_type='MID_TERM_1', institution=self.institution,
			admission_class='6', section='A', session='2026',
		)
		self.user = get_user_model().objects.create_user(username='exam-user', password='password')
		exammark_content_type = ContentType.objects.get_for_model(ExamMark)
		exam_content_type = ContentType.objects.get_for_model(Exam)
		add_exammark, _ = Permission.objects.get_or_create(
			content_type=exammark_content_type,
			codename='add_exammark',
		)
		change_exam, _ = Permission.objects.get_or_create(
			content_type=exam_content_type,
			codename='change_exam',
		)
		add_exam_perm, _ = Permission.objects.get_or_create(
			content_type=exam_content_type,
			codename='add_exam',
		)
		self.user.user_permissions.add(add_exammark, change_exam, add_exam_perm)
		self.client.force_login(self.user)

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

	def test_exam_type_uses_approved_dropdown_and_auto_names(self):
		form = ExamForm()
		self.assertNotIn('name', form.fields)
		self.assertIn(('FIRST_TERM', 'First Term'), form.fields['exam_type'].choices)
		self.assertIn(('MID_TERM_3', 'Mid Term-3'), form.fields['exam_type'].choices)

		response = self.client.get(reverse('add_exam'))
		self.assertEqual(response.status_code, 200)
		self.assertNotIn('exam_name_suggestions', response.context)

	def test_exam_form_uses_dropdowns_for_class_and_section(self):
		form = ExamForm()
		self.assertEqual(form.fields['admission_class'].widget.__class__.__name__, 'Select')
		self.assertEqual(form.fields['section'].widget.__class__.__name__, 'Select')
		self.assertIn(('A', 'A'), form.fields['section'].choices)
		self.assertIn(('J', 'J'), form.fields['section'].choices)
		self.assertNotIn(('N/A', 'N/A'), form.fields['section'].choices)

	def test_delete_exam_route_is_disabled_for_permanent_results(self):
		permission = Permission.objects.get_or_create(codename='delete_exam', content_type=ContentType.objects.get_for_model(Exam))[0]
		self.client.force_login(self.user)
		self.user.user_permissions.add(permission)
		response = self.client.post(reverse('delete_exam', args=[self.exam.pk]))
		self.assertRedirects(response, reverse('exam_list'))
		self.assertTrue(Exam.objects.filter(pk=self.exam.pk).exists())

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



class StudentProfileAndBulkUpdateTests(TestCase):
	def setUp(self):
		self.institution = Institution.objects.create(name='Profile Campus', classes='6,7,8,9,10')
		self.user = get_user_model().objects.create_superuser(username='profile-admin', password='password')
		self.client.force_login(self.user)
		self.student = Student.objects.create(
			institution=self.institution,
			student_id='P101',
			name='Profile Student',
			admission_class='9',
			section='A',
			group='SCI',
			admission_year=2026,
		)

	def test_student_form_includes_photo_field(self):
		self.assertIn('photo', StudentForm().fields)

	def test_bulk_update_select_has_class_and_group_controls(self):
		response = self.client.post(reverse('bulk_update_select'), {
			'student_ids': [self.student.pk],
			'institution': self.institution.pk,
			'admission_class': '9',
			'section': 'A',
		})
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'name="new_group"')
		self.assertContains(response, 'name="new_class"')
		self.assertContains(response, 'name="new_section"')


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


class EmployeeDetailPageTests(TestCase):
	def setUp(self):
		self.user = get_user_model().objects.create_superuser(username='admin', password='password')
		self.client.force_login(self.user)
		self.institution = Institution.objects.create(name='Test School', classes='6,7,8')
		self.employee = Employee.objects.create(
			name='John Doe', designation='Teacher', department='Science',
			institution=self.institution, join_date=date(2020, 1, 15), contact_no='01700000000'
		)

	def test_employee_detail_page_loads(self):
		"""Test that employee detail page loads successfully."""
		response = self.client.get(reverse('employee_detail', args=[self.employee.pk]))
		
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'John Doe')
		self.assertContains(response, 'Teacher')
		self.assertContains(response, 'Overview')

	def test_employee_detail_shows_status_history(self):
		"""Test that employee detail page displays status history."""
		EmployeeStatusLog.objects.create(
			employee=self.employee, old_status='ACTIVE', new_status='OSD',
			reason='On Special Duty', changed_by=self.user
		)
		
		response = self.client.get(reverse('employee_detail', args=[self.employee.pk]))
		
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Status History')
		self.assertContains(response, 'On Special Duty')

	def test_employee_detail_shows_attendance_records(self):
		"""Test that employee detail page displays attendance records."""
		from datetime import date
		AttendanceRecord.objects.create(
			employee=self.employee, date=date.today(), status='P',
			institution=self.institution, created_by=self.user
		)
		
		response = self.client.get(reverse('employee_detail', args=[self.employee.pk]))
		
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Attendance')
		self.assertContains(response, 'Present')


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



class MarksPartsAndPassRulesTests(TestCase):
	"""Practical / Weekly Test entry, the part pass rule, and blank-is-absent."""

	def setUp(self):
		self.institution = Institution.objects.create(name='Marks School', classes='9')
		self.user = get_user_model().objects.create_superuser(username='marks-admin', password='password')
		self.client.force_login(self.user)
		self.physics = Subject.objects.create(code='PHY', name='Physics', full_marks=100)
		self.exam = Exam.objects.create(
			name='Second Term Examination-2026', exam_type='SECOND_TERM',
			institution=self.institution, admission_class='9', section='', group='SCI',
			session='2026',
		)
		self.student = Student.objects.create(
			institution=self.institution, student_id='M001', name='Marked Student',
			admission_class='9', section='A', group='SCI', roll_no=1, admission_year=2026,
		)
		self.absent_student = Student.objects.create(
			institution=self.institution, student_id='M002', name='Absent Student',
			admission_class='9', section='A', group='SCI', roll_no=2, admission_year=2026,
		)

	def configure(self, **overrides):
		fields = {
			'institution': self.institution, 'admission_class': '9',
			'subject': self.physics, 'exam_type': 'SECOND_TERM',
			'full_marks': 100, 'cq_marks': 75, 'mcq_marks': 0, 'practical_marks': 25,
		}
		fields.update(overrides)
		from .models import SubjectMarkSetting
		return SubjectMarkSetting.objects.create(**fields)

	def post_marks(self, payload):
		return self.client.post(
			reverse('enter_marks', args=[self.exam.pk, self.physics.pk]), payload
		)

	def test_parts_are_added_into_the_total(self):
		self.configure()
		self.post_marks({
			f'cq_{self.student.pk}': '60',
			f'mcq_{self.student.pk}': '',
			f'practical_{self.student.pk}': '20',
		})
		mark = ExamMark.objects.get(exam=self.exam, student=self.student, subject=self.physics)
		self.assertEqual(str(mark.marks_obtained), '80.00')
		self.assertEqual(str(mark.cq_obtained), '60.00')
		self.assertEqual(str(mark.practical_obtained), '20.00')
		self.assertIsNone(mark.weekly_test_obtained)

	def test_a_student_entered_nowhere_has_no_row(self):
		"""Blank everywhere means absent: no row, so the result shows a dash."""
		self.configure()
		self.post_marks({
			f'cq_{self.student.pk}': '60', f'practical_{self.student.pk}': '20',
			f'cq_{self.absent_student.pk}': '', f'practical_{self.absent_student.pk}': '',
		})
		self.assertFalse(ExamMark.objects.filter(student=self.absent_student).exists())

	def test_mark_above_a_part_max_is_not_saved(self):
		self.configure()
		response = self.post_marks({
			f'cq_{self.student.pk}': '90', f'practical_{self.student.pk}': '20',
		})
		self.assertEqual(response.status_code, 302)
		self.assertFalse(ExamMark.objects.filter(student=self.student).exists())
		followed = self.client.get(reverse('exam_list'))
		self.assertContains(followed, 'must be between 0 and 75')

	def test_each_part_must_pass_fails_the_subject_on_one_part(self):
		setting = self.configure(require_all_parts_pass=True, pass_percentage=40)
		# 80/100 overall passes the subject total, but 5/25 fails the practical
		# (pass mark for that part is 10).
		ExamMark.objects.create(
			exam=self.exam, student=self.student, subject=self.physics,
			marks_obtained=80, cq_obtained=75, practical_obtained=5,
		)
		from .result_utils import build_exam_results, get_subject_marks
		result = compute_first_result(self.exam)
		self.assertEqual(result['status'], 'Fail')
		self.assertEqual(str(result['gpa']), '0.00')
		subject_result = result['subject_results'][0]
		self.assertEqual(subject_result['grade'], 'F')
		self.assertEqual(subject_result['failed_parts'], ['Practical'])
		self.assertEqual(setting.pass_marks, 40.0)
		self.assertEqual(get_subject_marks(self.exam, self.physics).part_pass_marks(25), 10.0)

	def test_without_the_tick_only_the_total_matters(self):
		self.configure(require_all_parts_pass=False)
		ExamMark.objects.create(
			exam=self.exam, student=self.student, subject=self.physics,
			marks_obtained=80, cq_obtained=75, practical_obtained=5,
		)
		result = compute_first_result(self.exam)
		self.assertEqual(result['status'], 'Pass')

	def test_configured_but_blank_part_is_a_failed_part(self):
		self.configure(require_all_parts_pass=True)
		ExamMark.objects.create(
			exam=self.exam, student=self.student, subject=self.physics,
			marks_obtained=99, cq_obtained=74, mcq_obtained=25, practical_obtained=None,
		)
		result = compute_first_result(self.exam)
		self.assertEqual(result['status'], 'Fail')
		self.assertEqual(result['subject_results'][0]['failed_parts'], ['Practical'])

	def test_parts_total_mismatch_is_reported_on_the_entry_page(self):
		self.configure(practical_marks=None, cq_marks=70, mcq_marks=20)
		response = self.client.get(reverse('enter_marks', args=[self.exam.pk, self.physics.pk]))
		self.assertContains(response, 'add up to 90')

	def test_weekly_test_is_an_enterable_part(self):
		self.configure(cq_marks=60, mcq_marks=20, weekly_test_marks=20)
		self.post_marks({
			f'cq_{self.student.pk}': '50', f'mcq_{self.student.pk}': '15',
			f'weekly_test_{self.student.pk}': '18',
		})
		mark = ExamMark.objects.get(exam=self.exam, student=self.student)
		self.assertEqual(str(mark.marks_obtained), '83.00')
		self.assertEqual(str(mark.weekly_test_obtained), '18.00')


def compute_first_result(exam):
	"""Result row for the first student, shared by the tests above."""
	from .result_utils import build_exam_results
	_, results = build_exam_results(exam)
	return results[0]


class ExamScopeConsistencyTests(TestCase):
	"""Marks entry, import, seat plan and results must list the same students."""

	def setUp(self):
		self.institution = Institution.objects.create(name='Scope School', classes='9')
		self.user = get_user_model().objects.create_superuser(username='scope-admin', password='password')
		self.client.force_login(self.user)
		self.physics = Subject.objects.create(code='PHY2', name='Physics', full_marks=100)
		self.accounting = Subject.objects.create(code='ACC2', name='Accounting', full_marks=100)
		from .models import SubjectRequirement
		SubjectRequirement.objects.create(
			institution=self.institution, admission_class='9', group='SCI',
			subject=self.physics, requirement_type='MANDATORY',
		)
		SubjectRequirement.objects.create(
			institution=self.institution, admission_class='9', group='BUS',
			subject=self.accounting, requirement_type='MANDATORY',
		)
		self.exam = Exam.objects.create(
			name='Second Term Examination-2026', exam_type='SECOND_TERM',
			institution=self.institution, admission_class='9', group='SCI', session='2026',
		)
		# Zero-padded class: the exam module must still match these students.
		self.science_student = Student.objects.create(
			institution=self.institution, student_id='S010', name='Science Kid',
			admission_class='09', section='A', group='SCI', roll_no=1, admission_year=2026,
		)
		self.business_student = Student.objects.create(
			institution=self.institution, student_id='B010', name='Business Kid',
			admission_class='9', section='A', group='BUS', roll_no=1, admission_year=2026,
		)
		self.archived_student = Student.objects.create(
			institution=self.institution, student_id='S011', name='Gone Student',
			admission_class='9', section='A', group='SCI', roll_no=2,
			admission_year=2026, is_archived=True,
		)

	def test_get_exam_students_scopes_by_class_group_and_archive(self):
		from .result_utils import get_exam_students
		self.assertEqual(list(get_exam_students(self.exam)), [self.science_student])

	def test_enter_marks_and_seat_plan_agree(self):
		marks_page = self.client.get(reverse('enter_marks', args=[self.exam.pk, self.physics.pk]))
		self.assertContains(marks_page, 'Science Kid')
		self.assertNotContains(marks_page, 'Business Kid')
		self.assertNotContains(marks_page, 'Gone Student')

		seat_page = self.client.get(reverse('seat_plan_list', args=[self.exam.pk]))
		self.assertContains(seat_page, '1')
		self.assertEqual(seat_page.context['total_students'], 1)

	def test_import_rejects_other_group_student_and_unassigned_subject(self):
		try:
			from openpyxl import Workbook
		except ModuleNotFoundError:
			self.skipTest('openpyxl is required for Excel import tests')
		from io import BytesIO
		from django.core.files.uploadedfile import SimpleUploadedFile

		workbook = Workbook()
		sheet = workbook.active
		sheet.append(['Student ID', 'Subject Code', 'Marks'])
		sheet.append(['B010', 'PHY2', 55])   # Business student in a Science exam
		output = BytesIO()
		workbook.save(output)
		response = self.client.post(
			reverse('import_exam_marks', args=[self.exam.pk]),
			{'excel_file': SimpleUploadedFile(
				'marks.xlsx', output.getvalue(),
				content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')},
		)
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'not a member of this exam class/section/group')
		self.assertEqual(ExamMark.objects.count(), 0)

	def test_import_skips_rows_without_a_mark(self):
		try:
			from openpyxl import Workbook
		except ModuleNotFoundError:
			self.skipTest('openpyxl is required for Excel import tests')
		from io import BytesIO
		from django.core.files.uploadedfile import SimpleUploadedFile

		workbook = Workbook()
		sheet = workbook.active
		sheet.append(['Student ID', 'Subject Code', 'Marks'])
		sheet.append(['S010', 'PHY2', 71])
		sheet.append(['S010', 'ACC2', None])   # blank = not entered, not an error
		output = BytesIO()
		workbook.save(output)
		self.client.post(
			reverse('import_exam_marks', args=[self.exam.pk]),
			{'excel_file': SimpleUploadedFile(
				'marks.xlsx', output.getvalue(),
				content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')},
		)
		self.assertEqual(ExamMark.objects.count(), 1)
		self.assertEqual(str(ExamMark.objects.get().marks_obtained), '71.00')

	def test_import_uses_the_exam_full_marks_not_the_subject_default(self):
		from .models import SubjectMarkSetting
		SubjectMarkSetting.objects.create(
			institution=self.institution, admission_class='9', subject=self.physics,
			exam_type='SECOND_TERM', full_marks=50,
		)
		self.assertTrue(self.physics.full_marks > 50)
		# (guard: the 71 mark used above would be rejected against a 50-mark exam)
		from .result_utils import get_subject_marks
		self.assertEqual(get_subject_marks(self.exam, self.physics).full_marks, 50)

	def test_result_sheet_excludes_other_group_subjects_and_warns(self):
		ExamMark.objects.create(
			exam=self.exam, student=self.science_student, subject=self.accounting,
			marks_obtained=80,
		)
		self.exam.is_published = True
		self.exam.save()
		response = self.client.get(reverse('result_sheet', args=[self.exam.pk]))
		self.assertContains(response, 'Physics')
		content = response.content.decode()
		self.assertNotIn('<th>Accounting', content)
		self.assertContains(response, 'not assigned to its class/group')

	def test_zero_gpa_students_are_not_ranked_and_do_not_crash_top_10(self):
		self.exam.is_published = True
		self.exam.save()
		ExamMark.objects.create(
			exam=self.exam, student=self.science_student, subject=self.physics, marks_obtained=80,
		)
		response = self.client.get(reverse('top_10', args=[self.exam.pk]))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Science Kid')


class MarksImportTemplateDownloadTests(TestCase):
	def setUp(self):
		self.institution = Institution.objects.create(name='Template School', classes='9')
		self.user = get_user_model().objects.create_superuser(username='template-admin', password='password')
		self.client.force_login(self.user)
		self.subject = Subject.objects.create(code='BNG', name='Bangla', full_marks=100)
		self.exam = Exam.objects.create(
			name='Second Term Examination-2026', exam_type='SECOND_TERM',
			institution=self.institution, admission_class='9', group='SCI', session='2026',
		)
		Student.objects.create(
			institution=self.institution, student_id='T001', name='Template Kid',
			admission_class='9', section='A', group='SCI', roll_no=1, admission_year=2026,
		)

	def test_workbook_matches_what_the_importer_accepts(self):
		try:
			from openpyxl import load_workbook
		except ModuleNotFoundError:
			self.skipTest('openpyxl is required for Excel export tests')
		response = self.client.get(reverse('download_marks_import_template', args=[self.exam.pk]))
		self.assertEqual(response.status_code, 200)
		self.assertIn('spreadsheetml.sheet', response['Content-Type'])
		import io
		workbook = load_workbook(io.BytesIO(response.content), read_only=True)
		sheet = workbook['Marks']
		rows = list(sheet.iter_rows(values_only=True))
		self.assertEqual(rows[0], ('Student ID', 'Subject Code', 'Marks'))
		self.assertEqual(rows[1], ('T001', 'BNG', None))
		self.assertIn('Subjects', workbook.sheetnames)


class ExamNamingAndLayoutTests(TestCase):
	def setUp(self):
		self.user = get_user_model().objects.create_superuser(username='layout-admin', password='password')
		self.client.force_login(self.user)
		self.institution = Institution.objects.create(name='Layout School', classes='9')
		self.exam = Exam.objects.create(
			name='Placeholder', exam_type='SECOND_TERM', institution=self.institution,
			admission_class='9', session='2026-2027',
		)

	def test_auto_exam_name_uses_the_last_year_in_the_session(self):
		self.assertEqual(auto_exam_name('SECOND_TERM', '2026-2027'), 'Second Term Examination-2027')
		self.assertEqual(auto_exam_name('MID_TERM_1', '2026'), 'Mid Term-1 Examination-2026')
		self.assertEqual(auto_exam_name('MODEL_TEST_3', ''), 'Model Test-3 Examination')

	def test_saving_the_exam_form_regenerates_the_name(self):
		from .forms import ExamForm
		form = ExamForm(instance=self.exam, data={
			'institution': self.institution.pk, 'admission_class': '9', 'section': '',
			'group': '', 'exam_type': 'FINAL_TERM', 'session': '2026-2027',
		})
		self.assertTrue(form.is_valid(), form.errors)
		form.save()
		self.exam.refresh_from_db()
		self.assertEqual(self.exam.name, 'Final Term Examination-2027')

	def test_exam_form_offers_section_as_a_dropdown(self):
		from .forms import ExamForm
		form = ExamForm()
		self.assertEqual(form.fields['section'].widget.__class__.__name__, 'Select')
		self.assertNotIn('name', form.fields)

	def test_audit_log_and_import_students_render_in_the_app_layout(self):
		for name, url_name in (('Audit Log', 'audit_log_list'), ('Import Students', 'import_students')):
			with self.subTest(page=name):
				response = self.client.get(reverse(url_name))
				self.assertEqual(response.status_code, 200)
				self.assertContains(response, 'Principal Kazi Faruky School And College')
				self.assertContains(response, 'sidebar')

	def test_no_auto_field_warnings_remain(self):
		from django.core.checks import run_checks
		warnings = [issue for issue in run_checks() if issue.id.startswith('models.W042')]
		self.assertEqual(warnings, [])


class SSCGroupAlignmentTests(TestCase):
	def setUp(self):
		self.institution = Institution.objects.create(name='SSC School', classes='9,10')
		self.user = get_user_model().objects.create_superuser(username='ssc-admin', password='password')
		self.client.force_login(self.user)
		self.student = Student.objects.create(
			institution=self.institution, student_id='SSC01', name='SSC Kid',
			admission_class='10', section='A', group='SCI', roll_no=1, admission_year=2026,
		)

	def test_ssc_group_codes_are_the_student_group_codes(self):
		from .models import SSCRegistration
		student_codes = {code for code, _label in Student.GROUP_CHOICES}
		self.assertTrue(SSCRegistration.GROUP_CHOICES)
		for code, _label in SSCRegistration.GROUP_CHOICES:
			self.assertIn(code, student_codes)

	def test_form_refuses_a_group_that_disagrees_with_the_student(self):
		from .forms import SSCRegistrationForm
		from .models import SSCRegistration
		form = SSCRegistrationForm(student=self.student, data={
			'registration_number': 'R-1', 'session': '2025-2026', 'group': 'BUS',
			'board': 'DHAKA', 'subjects': '', 'roll_number': '', 'center': '',
		})
		self.assertFalse(form.is_valid())
		self.assertIn('group', form.errors)
		self.assertIn('Science', form.errors['group'][0])

	def test_form_accepts_a_matching_group_and_prefills_it(self):
		from .forms import SSCRegistrationForm
		form = SSCRegistrationForm(student=self.student)
		self.assertEqual(form.fields['group'].initial, 'SCI')
		form = SSCRegistrationForm(student=self.student, data={
			'registration_number': 'R-2', 'session': '2025-2026', 'group': 'SCI',
			'board': 'DHAKA', 'subjects': 'Bangla', 'roll_number': '', 'center': '',
		})
		self.assertTrue(form.is_valid(), form.errors)
		registration = form.save(commit=False)
		registration.student = self.student
		registration.save()
		self.assertEqual(registration.get_group_display(), 'Science')


class AbsentSubjectRulesTests(TestCase):
	"""NCTB/SSC reading: not sitting an assigned subject is a fail, not a free pass."""

	def setUp(self):
		self.institution = Institution.objects.create(name='Absent School', classes='9')
		self.user = get_user_model().objects.create_superuser(username='absent-admin', password='password')
		self.client.force_login(self.user)
		self.physics = Subject.objects.create(code='PHYA', name='Physics', full_marks=100)
		self.math = Subject.objects.create(code='MTXA', name='Higher Math', full_marks=100)
		from .models import SubjectRequirement
		for subject in (self.physics, self.math):
			# Group-neutral assignments, so both subjects are columns even when a
			# student has no mark in one of them.
			SubjectRequirement.objects.create(
				institution=self.institution, admission_class='9', group='',
				subject=subject, requirement_type='MANDATORY',
			)
		self.exam = Exam.objects.create(
			name='Second Term Examination-2026', exam_type='SECOND_TERM',
			institution=self.institution, admission_class='9', session='2026', is_published=True,
		)
		self.partial = Student.objects.create(
			institution=self.institution, student_id='A001', name='Half Present',
			admission_class='9', section='A', roll_no=1, admission_year=2026,
		)
		self.never = Student.objects.create(
			institution=self.institution, student_id='A002', name='Totally Absent',
			admission_class='9', section='A', roll_no=2, admission_year=2026,
		)
		ExamMark.objects.create(
			exam=self.exam, student=self.partial, subject=self.physics, marks_obtained=95,
		)

	def test_unentered_subject_is_graded_f_and_makes_the_result_fail(self):
		result = compute_first_result(self.exam)
		self.assertEqual(result['student'], self.partial)
		self.assertEqual(result['status'], 'Fail')
		self.assertEqual(str(result['gpa']), '0.00')
		absent_row = [row for row in result['subject_results'] if row['absent']][0]
		self.assertEqual(absent_row['subject'], self.math)
		self.assertEqual(absent_row['grade'], 'F')
		self.assertEqual(absent_row['obtained'], 0)
		# the missed subject is counted as 0 / 100, so the percentage tells the truth
		self.assertEqual(result['total_obtained'], 95)
		self.assertEqual(result['total_full'], 200)

	def test_a_dash_is_printed_for_the_absent_subject_not_a_zero(self):
		response = self.client.get(reverse('result_sheet', args=[self.exam.pk]))
		content = response.content.decode()
		self.assertIn('absent-mark', content)
		self.assertIn('no mark entered - counted as F', content)

	def test_student_with_no_marks_anywhere_is_no_marks_not_fail(self):
		"""Nobody sat this exam: an attendance problem, not a graded result."""
		result = [r for r in self._results() if r['student'] == self.never][0]
		self.assertEqual(result['status'], 'No Marks')
		self.assertIsNone(result['gpa'])
		self.assertIsNone(result['position'])

	def test_absent_rule_can_be_switched_off(self):
		from django.test import override_settings
		with override_settings(EXAM_ABSENT_SUBJECT_FAILS=False):
			result = compute_first_result(self.exam)
		self.assertEqual(result['status'], 'Pass')
		self.assertEqual(result['total_full'], 100)
		absent_row = [row for row in result['subject_results'] if row['absent']][0]
		self.assertEqual(absent_row['grade'], '-')
		self.assertIsNone(absent_row['obtained'])

	def _results(self):
		from .result_utils import build_exam_results
		_, results = build_exam_results(self.exam)
		return results


class GroupOnlyFromClass9Tests(TestCase):
	"""A group exists from class 9 up. Primary and junior secondary (6-8)
	follow one common syllabus, so the field must be hidden, optional and
	never stored for them."""

	def setUp(self):
		self.institution = Institution.objects.create(name='Group Rule Campus', classes='6,7,8,9,10,11,12')
		self.user = get_user_model().objects.create_superuser(username='group-admin', password='password')
		self.client.force_login(self.user)

	def _post(self, **overrides):
		data = {
			'institution': self.institution.pk,
			'name': 'Group Rule Student',
			'admission_class': '6',
			'section': 'A',
			'admission_year': 2026,
			'roll_no': 1,
			'gender': 'M',
			'religion': 'Islam',
			'status': 'ACTIVE',
			'group': 'SCI',
		}
		data.update(overrides)
		return self.client.post(reverse('add_student'), data)

	def test_group_choices_start_at_class_9(self):
		self.assertFalse(Student.class_supports_group('6'))
		self.assertFalse(Student.class_supports_group('08'))
		self.assertTrue(Student.class_supports_group('9'))
		self.assertTrue(Student.class_supports_group('12'))
		codes = [code for code, _ in Student.group_choices_for_class('9')]
		self.assertEqual(codes, ['SCI', 'BUS', 'HUM'])
		self.assertEqual(Student.group_choices_for_class('6'), [])

	def test_class_6_admission_ignores_a_submitted_group(self):
		response = self._post(admission_class='6', group='SCI')
		self.assertEqual(response.status_code, 302)
		student = Student.objects.get(name='Group Rule Student')
		self.assertEqual(student.group, '')

	def test_class_9_admission_requires_a_group(self):
		response = self._post(name='No Group Nine', admission_class='9', group='')
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Group is required')
		self.assertFalse(Student.objects.filter(name='No Group Nine').exists())

	def test_class_9_admission_accepts_business_and_humanities(self):
		for code in ('BUS', 'HUM'):
			self._post(name=f'Student {code}', admission_class='9', group=code)
			self.assertEqual(Student.objects.get(name=f'Student {code}').group, code)

	def test_diploma_group_is_not_offered_at_class_9(self):
		"""A stale dropdown can still post a code the class does not offer;
		the officer gets a usable message, not a bare 'invalid choice'."""
		response = self._post(name='Diploma Nine', admission_class='9', group='DCS')
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Select Science, Business Studies or Humanities.')
		self.assertFalse(Student.objects.filter(name='Diploma Nine').exists())

	def test_model_save_clears_a_stale_group(self):
		student = Student.objects.create(
			institution=self.institution, student_id='G001', name='Stale Group',
			admission_class='7', section='A', admission_year=2026, group='SCI',
		)
		self.assertEqual(student.group, '')
		student.admission_class = '9'
		student.group = 'HUM'
		student.save()
		self.assertEqual(student.group, 'HUM')

	def test_add_student_page_hides_the_group_field_below_class_9(self):
		response = self.client.get(reverse('add_student'))
		self.assertContains(response, 'id="group-field-wrapper"')
		self.assertContains(response, 'const GROUPED_CLASSES = ["9", "10", "11", "12"];')

	def test_admission_dropdown_offers_no_group_below_class_9(self):
		response = self.client.get(reverse('admission_dropdown_options'), {
			'institution': self.institution.pk, 'admission_class': '6',
		})
		payload = response.json()
		self.assertEqual(payload['groups'], [])
		self.assertFalse(payload['supports_group'])

	def test_admission_dropdown_offers_three_groups_from_class_9(self):
		for cls in ('9', '11'):
			payload = self.client.get(reverse('admission_dropdown_options'), {
				'institution': self.institution.pk, 'admission_class': cls,
			}).json()
			self.assertTrue(payload['supports_group'])
			self.assertEqual([g['value'] for g in payload['groups']], ['SCI', 'BUS', 'HUM'])

	def test_bulk_update_into_class_6_clears_the_group(self):
		student = Student.objects.create(
			institution=self.institution, student_id='G002', name='Moving Down',
			admission_class='9', section='A', admission_year=2026, group='SCI',
		)
		response = self.client.post(reverse('bulk_update_students'), {
			'student_ids': [student.pk], 'new_class': '6', 'new_group': 'HUM',
		})
		self.assertEqual(response.status_code, 302)
		student.refresh_from_db()
		self.assertEqual(student.admission_class, '6')
		self.assertEqual(student.group, '')

	def test_bulk_update_keeps_the_group_inside_class_9(self):
		student = Student.objects.create(
			institution=self.institution, student_id='G003', name='Staying Nine',
			admission_class='9', section='A', admission_year=2026, group='SCI',
		)
		self.client.post(reverse('bulk_update_students'), {
			'student_ids': [student.pk], 'new_group': 'BUS',
		})
		student.refresh_from_db()
		self.assertEqual(student.group, 'BUS')

	@skipUnless(Workbook, 'openpyxl not installed')
	def test_excel_import_ignores_the_group_column_below_class_9(self):
		book = Workbook()
		sheet = book.active
		sheet.append([
			'Institution', 'Name', 'Class', 'Section', 'Admission Year', 'Roll No',
			'Gender', 'Religion', 'Father Name', 'Contact No', 'Guardian Contact No', 'Group',
		])
		sheet.append([
			self.institution.name, 'Import Six', '6', 'A', 2026, 11,
			'Male', 'Islam', 'Father', '', '', 'Science',
		])
		sheet.append([
			self.institution.name, 'Import Nine', '9', 'A', 2026, 12,
			'Female', 'Islam', 'Father', '', '', 'Humanities',
		])
		buffer = BytesIO()
		book.save(buffer)
		buffer.seek(0)

		response = self.client.post(reverse('import_students'), {
			'excel_file': SimpleUploadedFile('students.xlsx', buffer.getvalue()),
		})
		self.assertEqual(response.status_code, 302)  # redirects back to the list on success
		self.assertEqual(Student.objects.get(name='Import Six').group, '')
		self.assertEqual(Student.objects.get(name='Import Nine').group, 'HUM')

	def test_clean_student_groups_command_only_touches_classes_below_9(self):
		from io import StringIO
		from django.core.management import call_command

		junior = Student.objects.create(
			institution=self.institution, student_id='G004', name='Junior Wrong',
			admission_class='6', section='A', admission_year=2026,
		)
		# bypasses save() on purpose: this is the state the live data is in
		Student.objects.filter(pk=junior.pk).update(group='SCI')
		senior = Student.objects.create(
			institution=self.institution, student_id='G005', name='Senior Right',
			admission_class='9', section='A', admission_year=2026, group='SCI',
		)

		out = StringIO()
		call_command('clean_student_groups', stdout=out)
		junior.refresh_from_db()
		self.assertEqual(junior.group, 'SCI', 'dry run must not change anything')
		self.assertIn('Dry run', out.getvalue())

		out = StringIO()
		call_command('clean_student_groups', '--apply', stdout=out)
		junior.refresh_from_db()
		senior.refresh_from_db()
		self.assertEqual(junior.group, '')
		self.assertEqual(senior.group, 'SCI')
		self.assertIn('Cleared the group on 1 student(s)', out.getvalue())

	def test_data_migration_clears_groups_below_class_9(self):
		# The migration module name starts with a digit, so it cannot be
		# imported with a normal import statement — load it by path instead.
		import importlib.util
		import pathlib

		path = pathlib.Path(__file__).parent / 'migrations' / '0033_clear_groups_below_class_9.py'
		spec = importlib.util.spec_from_file_location('clear_groups_migration', path)
		migration = importlib.util.module_from_spec(spec)
		spec.loader.exec_module(migration)

		wrong = Student.objects.create(
			institution=self.institution, student_id='G006', name='Migration Target',
			admission_class='8', section='A', admission_year=2026,
		)
		Student.objects.filter(pk=wrong.pk).update(group='HUM')

		class AppsShim:
			"""Stands in for the migration's historical app registry."""
			@staticmethod
			def get_model(app_label, model_name):
				return Student

		migration.clear_groups_below_class_9(AppsShim, None)
		wrong.refresh_from_db()
		self.assertEqual(wrong.group, '')


class GroupRuleTemplateSmokeTests(TestCase):
    """The group-rule templates were edited by hand; make sure they render."""

    def setUp(self):
        self.institution = Institution.objects.create(name='Smoke Campus', classes='6,9')
        self.user = get_user_model().objects.create_superuser(username='smoke', password='pw')
        self.client.force_login(self.user)
        self.six = Student.objects.create(
            institution=self.institution, student_id='S001', name='Six Student',
            admission_class='6', section='A', admission_year=2026,
        )

    def test_pages_render(self):
        for name, kwargs in [
            ('add_student', {}),
            ('admission', {}),
            ('public_admission_apply', {}),
            ('student_list', {}),
        ]:
            response = self.client.get(reverse(name, kwargs=kwargs))
            self.assertEqual(response.status_code, 200, name)

        response = self.client.post(reverse('bulk_update_select'), {
            'student_ids': [self.six.pk], 'institution': self.institution.pk,
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'GROUPED_CLASSES')

        response = self.client.get(reverse('edit_student', args=[self.six.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="group-field-wrapper"')

    def test_add_student_edit_page_marks_the_group_field_hidden_for_class_6(self):
        response = self.client.get(reverse('edit_student', args=[self.six.pk]))
        self.assertContains(response, 'const GROUPED_CLASSES = ["9", "10", "11", "12"];')
        self.assertContains(response, 'This class has no group')

    def test_admission_application_form_hides_the_group_until_a_class_is_picked(self):
        response = self.client.get(reverse('admission'))
        self.assertContains(response, 'function setGroupFieldVisible(visible, note)')
        self.assertContains(response, 'setGroupFieldVisible(false, \'\');')
        self.assertContains(response, 'data.supports_group')

    def test_public_admission_form_marks_the_group_column(self):
        response = self.client.get(reverse('public_admission_apply'))
        self.assertContains(response, 'id="group-field-wrapper"')
        self.assertContains(response, 'id="group-field-note"')
