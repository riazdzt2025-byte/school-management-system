"""Tests for P1-4: Attendance and Promotion entries in the sidebar navigation.

The links are gated by the related permission so a user lacking them does not
see the entries, while an authorised user (Office/Attendance) does.
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
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
