"""Tests for P1-4: Attendance and Promotion entries in the sidebar navigation.

The links are gated by the related permission so a user lacking them does not
see the entries, while an authorised user (Office/Attendance) does.
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from django.urls import reverse


class SidebarNavigationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='staff', password='password',
        )

    def _grant(self, codenames):
        for codename in codenames:
            perm = Permission.objects.get(codename=codename)
            self.user.user_permissions.add(perm)

    def test_authorised_user_sees_attendance_and_promotion(self):
        self._grant(['change_student', 'add_attendancerecord', 'view_attendancerecord'])
        self.client.force_login(self.user)
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        # The nav renders the group label and the links for authorised perms.
        self.assertIn('Attendance', body)
        self.assertIn(reverse('mark_attendance'), body)
        self.assertIn(reverse('attendance_report'), body)
        self.assertIn(reverse('attendance_summary'), body)
        self.assertIn(reverse('student_promotion'), body)

    def test_unauthorised_user_hides_attendance_and_promotion(self):
        # A user with no related permission must not see them.
        self.client.force_login(self.user)
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertNotIn(reverse('student_promotion'), body)
        self.assertNotIn(reverse('mark_attendance'), body)

    def test_no_attendance_perms_hides_attendance_group_but_keeps_exam(self):
        self._grant(['change_student'])
        self.client.force_login(self.user)
        response = self.client.get(reverse('dashboard'))
        body = response.content.decode()
        # Promotion visible (change_student), Attendance group hidden (no perm).
        self.assertIn(reverse('student_promotion'), body)
        self.assertNotIn('Attendance', body)
        self.assertNotIn(reverse('attendance_report'), body)

    def test_dashboard_quick_links_for_authorised_user(self):
        # P2-6: authorised user sees the quick-action links on the dashboard.
        self._grant(['add_student', 'view_admissionapplication',
                     'add_exammark', 'add_exam', 'add_moneyreceipt'])
        self.client.force_login(self.user)
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        for name in ['add_student', 'admission_application_list',
                     'start_entering_marks', 'add_exam', 'add_money_receipt']:
            self.assertIn(f'href="{reverse(name)}"', body, name)

    def test_dashboard_quick_links_hidden_without_perms(self):
        # A bare user sees no quick links (check the exact href anchor).
        self.client.force_login(self.user)
        response = self.client.get(reverse('dashboard'))
        body = response.content.decode()
        self.assertNotIn(f'href="{reverse("add_student")}"', body)
        self.assertNotIn('Quick actions', body)


class ExamAnalysisSubtabTests(TestCase):
    """EX-01: Analysis subtab inside the Exam flyout + cross-links, gate unchanged.

    The subtab links reuse the existing named URLs, so the Exam flyout and the
    standalone "Result Analysis" group are two entry points to the same pages;
    authorisation stays with the per-view server-side guard.
    """

    ANALYSIS_URL_NAMES = [
        'result_analysis_subject_fail',
        'result_analysis_multi_term',
        'result_analysis_merit_slides',
        'result_analysis_result_cards',
        'section_arrangement',
    ]

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='examclerk', password='password',
        )

    def _grant(self, codenames):
        for codename in codenames:
            perm = Permission.objects.get(codename=codename)
            self.user.user_permissions.add(perm)

    def test_exam_flyout_lists_analysis_links_for_authorised_user(self):
        # can_result_analysis is True for a legacy permission-based user.
        self._grant(['view_student'])
        self.client.force_login(self.user)
        response = self.client.get(reverse('dashboard'))
        body = response.content.decode()
        self.assertIn('class="flyout-subhead"', body)
        for name in self.ANALYSIS_URL_NAMES:
            url = reverse(name)
            self.assertIn(url, body, name)
            # Both entry points (Exam flyout subtab + standalone group) point at
            # the SAME named URL, so each href appears exactly twice.
            self.assertEqual(body.count(f'href="{url}"'), 2, name)

    def test_analysis_subtab_hidden_without_permission(self):
        # Viewing links you cannot open is a usability bug, not security.
        self.client.force_login(self.user)
        response = self.client.get(reverse('dashboard'))
        body = response.content.decode()
        self.assertNotIn('class="flyout-subhead"', body)
        for name in self.ANALYSIS_URL_NAMES:
            self.assertNotIn(reverse(name), body, name)

    def test_anonymous_user_is_redirected_to_login(self):
        for name in self.ANALYSIS_URL_NAMES:
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 302, name)
            self.assertIn('/login/', response.url, name)

    def test_guard_still_blocks_users_without_department(self):
        # Direct URL access: the per-view guard is the real security. A user
        # without perms, and an Accounts-only user WITH view_student, both
        # stay at 403 exactly as before the subtab existed.
        self.client.force_login(self.user)
        for name in self.ANALYSIS_URL_NAMES:
            self.assertEqual(self.client.get(reverse(name)).status_code, 403, name)
        accounts_group, _ = Group.objects.get_or_create(name='Accounts')
        self.user.groups.add(accounts_group)
        self._grant(['view_student'])
        for name in self.ANALYSIS_URL_NAMES:
            self.assertEqual(self.client.get(reverse(name)).status_code, 403, name)

    def test_authorised_user_reaches_every_analysis_page(self):
        self._grant(['view_student'])
        self.client.force_login(self.user)
        for name in self.ANALYSIS_URL_NAMES:
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)

    def test_exam_list_shows_analysis_entry_for_authorised_user(self):
        self._grant(['view_student'])
        self.client.force_login(self.user)
        response = self.client.get(reverse('exam_list'))
        body = response.content.decode()
        self.assertIn('analysis-entry', body)
        for name in self.ANALYSIS_URL_NAMES:
            self.assertIn(reverse(name), body, name)

    def test_exam_list_hides_analysis_entry_without_permission(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('exam_list'))
        body = response.content.decode()
        self.assertNotIn('analysis-entry', body)


class ResultPageAnalysisCrossLinkTests(TestCase):
    """EX-01: every result page header carries its relevant Analysis link."""

    @classmethod
    def setUpTestData(cls):
        from .models import (
            Exam, ExamMark, Institution, Student, Subject, SubjectRequirement,
        )
        cls.institution = Institution.objects.create(name='Nav School', classes='9')
        cls.admin = get_user_model().objects.create_superuser(
            username='nav-admin', email='a@example.com', password='password',
        )
        cls.plain = get_user_model().objects.create_user(
            username='nav-plain', password='password',
        )
        cls.subject = Subject.objects.create(code='HMATH', name='Higher Mathematics', full_marks=100)
        SubjectRequirement.objects.create(
            institution=cls.institution, admission_class='9', group='SCI',
            subject=cls.subject, requirement_type='MANDATORY',
        )
        cls.student = Student.objects.create(
            institution=cls.institution, student_id='NAV1', name='Nav Kid',
            admission_class='9', section='A', roll_no=1, group='SCI',
            admission_year=2026,
        )
        cls.exam = Exam.objects.create(
            name='First Term', exam_type='FIRST_TERM', institution=cls.institution,
            admission_class='9', group='SCI', session='2026', is_published=True,
        )
        ExamMark.objects.create(
            exam=cls.exam, student=cls.student, subject=cls.subject, marks_obtained=80,
        )

    def _assert_header_link(self, page_url, analysis_url_name, anchor_class):
        self.client.force_login(self.admin)
        body = self.client.get(page_url).content.decode()
        anchor = f'<a href="{reverse(analysis_url_name)}" class="{anchor_class}">'
        self.assertIn(anchor, body)
        self.client.force_login(self.plain)
        body = self.client.get(page_url).content.decode()
        self.assertNotIn('analysis-jump', body)

    def test_result_sheet_links_subject_fail_list(self):
        self._assert_header_link(
            reverse('result_sheet', args=[self.exam.pk]),
            'result_analysis_subject_fail',
            'btn btn-outline-navy btn-sm analysis-jump',
        )

    def test_result_summary_links_class_result_cards(self):
        self._assert_header_link(
            reverse('exam_result_summary', args=[self.exam.pk]),
            'result_analysis_result_cards',
            'btn btn-outline-navy btn-sm analysis-jump',
        )

    def test_full_rank_list_links_merit_slides(self):
        self._assert_header_link(
            reverse('full_rank_list', args=[self.exam.pk]),
            'result_analysis_merit_slides',
            'btn btn-outline-navy btn-sm analysis-jump',
        )

    def test_top_10_links_merit_slides(self):
        self._assert_header_link(
            reverse('top_10', args=[self.exam.pk]),
            'result_analysis_merit_slides',
            'btn btn-outline-navy btn-sm analysis-jump',
        )

    def test_student_result_detail_links_multi_term(self):
        self._assert_header_link(
            reverse('student_result_detail', args=[self.exam.pk, self.student.pk]),
            'result_analysis_multi_term',
            'btn btn-outline-navy analysis-jump',
        )
