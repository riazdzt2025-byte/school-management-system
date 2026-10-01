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
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import resolve, reverse

try:
	from openpyxl import Workbook
except ModuleNotFoundError:
	Workbook = None

from .models import (
	AuditLog, Exam, ExamMark, Institution, InstitutionAccess, Student, Subject, SubjectRequirement,
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
		self.assertNotContains(response, 'data-subject-pk')
		self.assertNotContains(response, 'data-enter-marks-base')
		self.assertNotContains(response, 'data-shortcut-disabled')
		self.assertNotContains(response, 'result_cell_shortcut.js')
		self.assertNotContains(response, 'correction-entry')
		self.assertEqual(response.context['enter_marks_base_url'], '')
		self.assertNotContains(response, reverse('enter_marks', args=[self.exam.pk, self.physics.pk]))
		self.assertEqual(self.client.get(reverse('enter_marks', args=[self.exam.pk, self.physics.pk])).status_code, 403)
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


	def _login_with_permission(self, codename='add_exammark'):
		user = get_user_model().objects.create_user(username=f'shortcut-{codename}')
		InstitutionAccess.objects.create(user=user, institution=self.institution, department='Exam')
		self.client.force_login(user)
		# Add after login so the tests isolate this permission from role sync.
		user.user_permissions.add(Permission.objects.get(codename=codename))
		return user

	def test_rank_list_has_no_hidden_correction_target_without_permission(self):
		viewer = get_user_model().objects.create_user(username='rank-viewer')
		self.client.force_login(viewer)
		response = self.client.get(reverse('full_rank_list', args=[self.exam.pk]), {'group': 'SCI'})
		self.assertEqual(response.status_code, 200)
		for text in ('data-shortcut-url', 'correction-entry', 'Ctrl/Cmd', 'result_cell_shortcut.js'):
			self.assertNotContains(response, text)
		self.assertEqual(response.context['marks_entry_url'], '')
		url = reverse('select_marks_subject', args=[self.exam.pk])
		self.assertNotContains(response, url)
		self.assertEqual(self.client.get(url).status_code, 403)

	def test_change_only_permission_is_not_enough_for_shortcut_or_server(self):
		self._login_with_permission('change_exammark')
		for view in ('result_sheet', 'full_rank_list'):
			response = self.client.get(reverse(view, args=[self.exam.pk]), {'group': 'SCI'})
			self.assertEqual(response.status_code, 200)
			for text in ('data-subject-pk', 'data-shortcut-url', 'data-enter-marks-base', 'correction-entry', 'Ctrl/Cmd'):
				self.assertNotContains(response, text)
		self.assertEqual(self.client.get(reverse('enter_marks', args=[self.exam.pk, self.physics.pk])).status_code, 403)

	def test_add_only_permission_renders_shortcut_and_keeps_published_lock(self):
		self._login_with_permission()
		for view in ('result_sheet', 'full_rank_list'):
			response = self.client.get(reverse(view, args=[self.exam.pk]), {'group': 'SCI'})
			self.assertContains(response, 'result_cell_shortcut.js')
			self.assertContains(response, 'correction-entry')
		url = reverse('enter_marks', args=[self.exam.pk, self.physics.pk]) + '?group=SCI'
		page = self.client.get(url)
		self.assertEqual(page.status_code, 200)
		self.assertTrue(page.context['published_lock']['locked'])
		self.client.post(url, {f'marks_{self.student.pk}': '99', 'group': 'SCI'})
		self.assertEqual(ExamMark.objects.get(exam=self.exam, subject=self.physics, student=self.student).marks_obtained, 74)
		self.assertTrue(AuditLog.objects.filter(action='exam_marks_write_blocked', object_id=str(self.exam.pk)).exists())

	def test_unpublished_result_pages_redirect_without_shortcut(self):
		self.client.force_login(self.admin)
		self.exam.is_published = False
		self.exam.save(update_fields=['is_published'])
		for view in ('result_sheet', 'full_rank_list'):
			response = self.client.get(reverse(view, args=[self.exam.pk]), {'group': 'SCI'})
			self.assertRedirects(response, reverse('exam_list'))
			self.assertNotContains(response, 'data-subject-pk', status_code=302)
			self.assertNotContains(response, 'data-shortcut-url', status_code=302)
		# Normal marks entry for an unpublished exam is still allowed, not a correction shortcut.
		page = self.client.get(reverse('enter_marks', args=[self.exam.pk, self.physics.pk]), {'group': 'SCI'})
		self.assertFalse(page.context['published_lock']['applies'])

	def test_visible_fallback_is_group_preserving_keyboard_accessible_and_print_hidden(self):
		from html.parser import HTMLParser

		class Links(HTMLParser):
			def __init__(self):
				super().__init__()
				self.links = []
			def handle_starttag(self, tag, attrs):
				attrs = dict(attrs)
				if tag == 'a' and 'correction-entry' in attrs.get('class', ''):
					self.links.append(attrs)

		self.client.force_login(self.admin)
		for view in ('result_sheet', 'full_rank_list'):
			response = self.client.get(reverse(view, args=[self.exam.pk]), {'group': 'SCI'})
			parser = Links()
			parser.feed(response.content.decode())
			self.assertEqual(len(parser.links), 1)
			self.assertEqual(parser.links[0]['href'], reverse('select_marks_subject', args=[self.exam.pk]) + '?group=SCI')
			self.assertEqual(parser.links[0]['target'], '_blank')
			self.assertEqual(parser.links[0]['rel'], 'noopener')
			self.assertContains(response, 'summary-actions d-print-none' if view == 'full_rank_list' else 'result-toolbar d-print-none')
			self.assertContains(response, 'Correct marks (choose subject)')

	def test_fixed_group_exam_uses_its_group_without_an_empty_querystring(self):
		self.client.force_login(self.admin)
		self.exam.group = 'SCI'
		self.exam.save(update_fields=['group'])
		response = self.client.get(reverse('result_sheet', args=[self.exam.pk]))
		self.assertEqual(response.context['selected_group'], '')
		self.assertContains(response, 'data-group=""')
		url = reverse('enter_marks', args=[self.exam.pk, self.physics.pk])
		page = self.client.get(url)
		self.assertEqual(page.context['exam'].group, 'SCI')
		self.assertEqual([r['student'].pk for r in page.context['students_with_marks']], [self.student.pk])
		rank = self.client.get(reverse('full_rank_list', args=[self.exam.pk]))
		self.assertEqual(rank.context['marks_entry_url'], reverse('select_marks_subject', args=[self.exam.pk]))

	def test_ungrouped_class_has_no_group_querystring(self):
		self.client.force_login(self.admin)
		self.exam.admission_class = '6'
		self.exam.save(update_fields=['admission_class'])
		self.student.admission_class = '6'
		self.student.group = ''
		self.student.save(update_fields=['admission_class', 'group'])
		SubjectRequirement.objects.filter(institution=self.institution).update(admission_class='6', group='')
		response = self.client.get(reverse('result_sheet', args=[self.exam.pk]))
		self.assertContains(response, 'data-group=""')
		self.assertEqual(response.context['group_querystring'], '')
		page = self.client.get(reverse('enter_marks', args=[self.exam.pk, self.physics.pk]))
		self.assertEqual(page.context['selected_group'], '')
		self.assertEqual([r['student'].pk for r in page.context['students_with_marks']], [self.student.pk])

	def test_other_institution_exam_tampering_is_404_for_reader_and_writer(self):
		self._login_with_permission()
		other = Institution.objects.create(name='Other Shortcut School', classes='9')
		exam = Exam.objects.create(name='Foreign Exam', exam_type='SECOND_TERM', institution=other,
			admission_class='9', session='2026', is_published=True)
		for view in ('result_sheet', 'full_rank_list', 'select_marks_subject'):
			self.assertEqual(self.client.get(reverse(view, args=[exam.pk])).status_code, 404)
		url = reverse('enter_marks', args=[exam.pk, self.physics.pk])
		self.assertEqual(self.client.get(url, {'group': 'SCI'}).status_code, 404)
		self.assertEqual(self.client.post(url, {f'marks_{self.student.pk}': '99'}).status_code, 404)
		self.assertFalse(ExamMark.objects.filter(exam=exam).exists())

	def test_subject_not_assigned_to_exam_cannot_be_written_by_url_tampering(self):
		self._login_with_permission()
		other_subject = Subject.objects.create(code='SCOTHER', name='Other Exam Subject', full_marks=100)
		url = reverse('enter_marks', args=[self.exam.pk, other_subject.pk])
		# Existing subject-scoping guard uses a polite redirect, not a 404.
		self.assertRedirects(self.client.get(url, {'group': 'SCI'}), reverse('select_marks_subject', args=[self.exam.pk]))
		self.assertEqual(self.client.post(url, {f'marks_{self.student.pk}': '99', 'group': 'SCI'}).status_code, 302)
		self.assertFalse(ExamMark.objects.filter(exam=self.exam, subject=other_subject).exists())

	def test_detail_and_card_remain_without_shortcut(self):
		self.client.force_login(self.admin)
		for view in ('student_result_detail', 'result_card'):
			response = self.client.get(reverse(view, args=[self.exam.pk, self.student.pk]))
			self.assertEqual(response.status_code, 200)
			for text in ('result_cell_shortcut.js', 'data-subject-pk', 'data-shortcut-url', 'correction-entry'):
				self.assertNotContains(response, text)
