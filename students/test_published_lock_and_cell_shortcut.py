"""R1 published-marks lock + E8 result-cell Ctrl/Cmd+Click correction shortcut.

R1: publishing makes a result official, so a published exam's marks are locked
until the user explicitly unlocks them; both the unlock and every refused write
are audited. Unpublishing removes the lock entirely.

E8: on a published result sheet, Ctrl/Cmd+Click a subject cell to open that
subject's marks entry in a new tab (the register stays open). The sheet only
exposes data — data-subject-pk / data-group / data-enter-marks-base — and the
click behaviour itself is unit-tested in students/js/result_cell_shortcut.test.js.
"""

from io import BytesIO
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import resolve, reverse

try:
	from openpyxl import Workbook
except ModuleNotFoundError:
	Workbook = None

from .models import (
	AuditLog, Exam, ExamMark, Institution, Student, Subject, SubjectRequirement,
)

WORKBOOK_CONTENT_TYPE = (
	'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
)


class PublishedMarksLockTests(TestCase):
	"""R1 — a published exam's marks are locked until explicitly unlocked."""

	def setUp(self):
		self.institution = Institution.objects.create(name='Lock School', classes='6,9')
		self.user = get_user_model().objects.create_superuser(
			username='lock-admin', password='password',
		)
		self.client.force_login(self.user)
		self.subject = Subject.objects.create(code='LCK1', name='LockSub', full_marks=100)
		SubjectRequirement.objects.create(
			institution=self.institution, admission_class='6',
			subject=self.subject, requirement_type='MANDATORY',
		)
		self.exam = Exam.objects.create(
			name='Lock Exam', exam_type='SECOND_TERM', institution=self.institution,
			admission_class='6', session='2026', is_published=True,
		)
		self.student = Student.objects.create(
			institution=self.institution, student_id='LCK001', name='Lock Kid',
			admission_class='6', section='A', roll_no=1, admission_year=2026,
		)

	def _marks_url(self):
		return reverse('enter_marks', args=[self.exam.pk, self.subject.pk])

	def _save_marks(self, value):
		return self.client.post(self._marks_url(), {f'marks_{self.student.pk}': value})

	def _audit(self, action):
		return AuditLog.objects.filter(action=action, object_id=str(self.exam.pk))

	def test_published_exam_blocks_marks_entry_until_unlocked(self):
		# The page states the marks are locked.
		page = self.client.get(self._marks_url())
		self.assertEqual(page.status_code, 200)
		self.assertTrue(page.context['published_lock']['locked'])
		self.assertContains(page, 'marks are locked')

		# A write is refused, audited, and stores nothing.
		response = self._save_marks('91')
		self.assertEqual(response.status_code, 302)
		self.assertEqual(ExamMark.objects.filter(exam=self.exam).count(), 0)
		self.assertTrue(self._audit('exam_marks_write_blocked').exists())

		# The explicit unlock is audited too, and saves nothing by itself.
		unlock = self.client.post(self._marks_url(), {'unlock_published_marks': '1'})
		self.assertEqual(unlock.status_code, 302)
		self.assertTrue(self._audit('exam_marks_unlocked').exists())
		self.assertEqual(ExamMark.objects.filter(exam=self.exam).count(), 0)

		# Only now does the same write go through.
		self.assertFalse(self.client.get(self._marks_url()).context['published_lock']['locked'])
		self._save_marks('91')
		mark = ExamMark.objects.get(exam=self.exam, student=self.student, subject=self.subject)
		self.assertEqual(mark.marks_obtained, 91)

	def test_unpublish_allows_entry_again(self):
		self.assertTrue(self.client.get(self._marks_url()).context['published_lock']['locked'])
		self.client.post(self._marks_url(), {'unlock_published_marks': '1'})
		self.assertFalse(self.client.get(self._marks_url()).context['published_lock']['locked'])

		# Unpublished: no lock, and the page stops advertising one.
		Exam.objects.filter(pk=self.exam.pk).update(is_published=False)
		page = self.client.get(self._marks_url())
		self.assertFalse(page.context['published_lock']['applies'])
		self.assertNotContains(page, 'marks are locked')
		self._save_marks('77')
		self.assertEqual(
			ExamMark.objects.get(exam=self.exam, student=self.student).marks_obtained, 77,
		)

		# Re-publishing starts locked again, even for this same session — the
		# stale unlock is dropped rather than inherited.
		Exam.objects.filter(pk=self.exam.pk).update(is_published=True)
		self.assertTrue(self.client.get(self._marks_url()).context['published_lock']['locked'])

	@skipUnless(Workbook, 'openpyxl is required for the Excel import')
	def test_published_lock_blocks_excel_import(self):
		url = reverse('import_exam_marks', args=[self.exam.pk])

		def upload():
			workbook = Workbook()
			sheet = workbook.active
			sheet.append(['Roll', 'ID', 'Name', 'Marks'])
			sheet.append([1, 'LCK001', 'Lock Kid', 88])
			payload = BytesIO()
			workbook.save(payload)
			return SimpleUploadedFile(
				'lock.xlsx', payload.getvalue(), content_type=WORKBOOK_CONTENT_TYPE,
			)

		response = self.client.post(
			url, {'subject': str(self.subject.pk), 'excel_file': upload()},
		)
		self.assertEqual(response.status_code, 302)
		self.assertEqual(ExamMark.objects.filter(exam=self.exam).count(), 0)
		self.assertTrue(self._audit('exam_marks_write_blocked').exists())

		self.client.post(url, {'unlock_published_marks': '1', 'subject': str(self.subject.pk)})
		self.client.post(url, {'subject': str(self.subject.pk), 'excel_file': upload()})
		self.assertEqual(
			ExamMark.objects.get(exam=self.exam, student=self.student).marks_obtained, 88,
		)

	@override_settings(EXAM_LOCK_PUBLISHED=False)
	def test_published_lock_can_be_switched_off_by_setting(self):
		page = self.client.get(self._marks_url())
		self.assertFalse(page.context['published_lock']['applies'])
		self.assertFalse(page.context['published_lock']['locked'])
		self._save_marks('65')
		self.assertEqual(
			ExamMark.objects.get(exam=self.exam, student=self.student).marks_obtained, 65,
		)
		self.assertFalse(self._audit('exam_marks_write_blocked').exists())


class ResultCellShortcutTests(TestCase):
	"""E8 — Ctrl/Cmd+Click a published result cell to reach its marks entry."""

	def setUp(self):
		self.institution = Institution.objects.create(name='Shortcut School', classes='9')
		self.admin = get_user_model().objects.create_superuser(
			username='shortcut-admin', password='password',
		)
		self.bangla = Subject.objects.create(code='SCB', name='Shortcut Bangla', full_marks=100)
		self.physics = Subject.objects.create(code='SCP', name='Shortcut Physics', full_marks=100)
		for subject in (self.bangla, self.physics):
			SubjectRequirement.objects.create(
				institution=self.institution, admission_class='9', group='SCI',
				subject=subject, requirement_type='MANDATORY',
			)
		# No group on the exam, so the sheet offers the group picker.
		self.exam = Exam.objects.create(
			name='Shortcut Exam', exam_type='SECOND_TERM', institution=self.institution,
			admission_class='9', session='2026', is_published=True,
		)
		self.student = Student.objects.create(
			institution=self.institution, student_id='SC001', name='Shortcut Kid',
			admission_class='9', section='A', roll_no=1, admission_year=2026, group='SCI',
		)
		ExamMark.objects.create(
			exam=self.exam, student=self.student, subject=self.bangla, marks_obtained=81,
		)
		ExamMark.objects.create(
			exam=self.exam, student=self.student, subject=self.physics, marks_obtained=74,
		)

	def test_result_cell_ctrl_click_url_resolves_with_group(self):
		self.client.force_login(self.admin)
		response = self.client.get(reverse('result_sheet', args=[self.exam.pk]), {'group': 'SCI'})
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'result_cell_shortcut.js')

		# Each cell carries its own subject pk and the group in view...
		self.assertContains(response, f'data-subject-pk="{self.physics.pk}"')
		self.assertContains(response, f'data-subject-pk="{self.bangla.pk}"')
		self.assertContains(response, 'data-group="SCI"')

		# ...and the base those are appended to is this exam's marks entry, so
		# the URL the page script builds is the canonical enter_marks URL.
		base = response.context['enter_marks_base_url']
		self.assertEqual(
			f'{base}{self.physics.pk}/',
			reverse('enter_marks', args=[self.exam.pk, self.physics.pk]),
		)
		match = resolve(f'{base}{self.physics.pk}/')
		self.assertEqual(match.view_name, 'enter_marks')
		self.assertEqual(match.kwargs, {'pk': self.exam.pk, 'subject_pk': self.physics.pk})

		# Following it with the group really opens that subject, for that group.
		page = self.client.get(f'{base}{self.physics.pk}/', {'group': 'SCI'})
		self.assertEqual(page.status_code, 200)
		self.assertEqual(page.context['selected_group'], 'SCI')
		self.assertEqual(page.context['subject'].pk, self.physics.pk)

	def test_result_cell_shortcut_is_disabled_without_marks_permission(self):
		viewer = get_user_model().objects.create_user(
			username='shortcut-viewer', password='password',
		)
		self.client.force_login(viewer)
		response = self.client.get(reverse('result_sheet', args=[self.exam.pk]), {'group': 'SCI'})
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'data-shortcut-disabled="true"')
		self.assertContains(response, 'Ask Exam dept')
		self.assertNotContains(response, 'Ctrl/Cmd+Click opens')

	def test_full_rank_list_row_links_to_the_exam_marks_entry(self):
		self.client.force_login(self.admin)
		response = self.client.get(
			reverse('full_rank_list', args=[self.exam.pk]), {'group': 'SCI'},
		)
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'result_cell_shortcut.js')
		url = response.context['marks_entry_url']
		# The rank list has no subject columns, so its shortcut opens this exam's
		# marks entry chooser, group preserved.
		self.assertEqual(url, reverse('select_marks_subject', args=[self.exam.pk]) + '?group=SCI')
		self.assertContains(response, f'data-shortcut-url="{url}"')
		match = resolve(reverse('select_marks_subject', args=[self.exam.pk]))
		self.assertEqual(match.view_name, 'select_marks_subject')
