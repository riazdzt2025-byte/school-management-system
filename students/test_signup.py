from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from .models import Employee, Institution, InstitutionAccess, SignupRequest
from .teacher_scope import is_teacher_account

TEMPLATES = Path(settings.BASE_DIR) / 'students' / 'templates' / 'students'
LOGIN_TEMPLATE = Path(settings.BASE_DIR) / 'school_system' / 'templates' / 'students' / 'login.html'


class SignupTests(TestCase):
    def setUp(self):
        cache.clear()
        self.institution = Institution.objects.create(name='School', number=7, classes='9')
        self.admin = get_user_model().objects.create_user('admin', password='test', is_staff=True)
        self.data = {
            'username': 'newteacher', 'email': 'teacher@example.com',
            'password1': 'A-strong-pass-915!', 'password2': 'A-strong-pass-915!',
            'full_name': 'New Teacher', 'institution': self.institution.pk,
            'department': 'Teacher', 'designation': 'Assistant Teacher',
            'contact_no': '01812345678', 'join_date': '2020-01-01',
        }

    def test_signup_page_renders_all_the_information(self):
        # The page is restyled (blue sliding card) but must keep every part of
        # the original information: heading, description, fields, submit
        # button, back link and title.
        response = self.client.get(reverse('signup'))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('<title>Teacher & Staff Sign up</title>', content)
        self.assertIn('শিক্ষক ও স্টাফ নিবন্ধন', content)
        self.assertIn('Teacher &amp; Staff Sign up — অ্যাডমিনের অনুমোদন ছাড়া সাইন ইন করা যাবে না', content)
        self.assertIn('Office, Exam or Accounts', content)
        for field in (
            'username', 'email', 'password1', 'password2', 'full_name',
            'institution', 'department', 'designation', 'contact_no', 'join_date',
        ):
            self.assertIn(f'name="{field}"', content)
        self.assertIn('Submit for approval', content)
        self.assertIn('Back to', content)
        self.assertIn(reverse('login'), content)
        # Every department offered on the login/signup dropdown.
        for department in ('Office', 'Exam', 'Accounts', 'Teacher'):
            self.assertIn(f'value="{department}"', content)

    def apply(self):
        response = self.client.post(reverse('signup'), self.data)
        self.assertRedirects(response, reverse('login'))
        return SignupRequest.objects.get()

    def test_registration_inactive_and_notifies_admin(self):
        application = self.apply()
        user = application.user
        self.assertFalse(user.is_active)
        self.assertTrue(user.check_password(self.data['password1']))
        self.assertFalse(Employee.objects.filter(user=user).exists())
        self.assertFalse(InstitutionAccess.objects.filter(user=user).exists())
        self.assertFalse(self.client.login(username=user.username, password=self.data['password1']))
        self.client.force_login(self.admin)
        response = self.client.get(reverse('signup_requests'))
        self.assertContains(response, 'New Teacher')
        self.assertEqual(response.context['pending_signup_count'], 1)

    def test_approval_creates_employee_and_enables_login_once(self):
        application = self.apply()
        self.client.force_login(self.admin)
        url = reverse('review_signup', args=[application.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.client.post(url, {'action': 'approve'})
        self.client.post(url, {'action': 'approve'})
        application.refresh_from_db()
        self.assertEqual(application.status, 'APPROVED')
        self.assertEqual(application.reviewed_by, self.admin)
        user = application.user
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_staff)
        self.assertEqual(Employee.objects.filter(user=user).count(), 1)
        self.assertTrue(InstitutionAccess.objects.filter(user=user, department='Teacher', is_active=True).exists())
        self.client.logout()
        response = self.client.post(reverse('login'), {
            'username': user.username, 'password': self.data['password1'],
            'institution_id': self.institution.pk, 'department': 'Teacher',
        })
        # The teacher lands on their classroom (the merged login page behaves
        # exactly like the old dedicated teacher login page did).
        self.assertRedirects(response, reverse('teacher_home'), fetch_redirect_response=False)

    def test_rejection_stays_inactive(self):
        application = self.apply()
        self.client.force_login(self.admin)
        url = reverse('review_signup', args=[application.pk])
        self.client.post(url, {'action': 'reject'})
        self.client.post(url, {'action': 'approve'})
        application.refresh_from_db()
        self.assertEqual(application.status, 'REJECTED')
        self.assertFalse(application.user.is_active)
        self.assertFalse(Employee.objects.exists())

    def test_nonadmin_cannot_review_or_see_requests(self):
        application = self.apply()
        user = get_user_model().objects.create_user('clerk', password='test')
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse('signup_requests')).status_code, 403)
        self.assertEqual(self.client.post(reverse('review_signup', args=[application.pk]), {'action': 'approve'}).status_code, 403)

    def test_staff_approval_is_not_teacher_or_admin(self):
        self.data.update(department='Accounts', designation='Accountant')
        application = self.apply()
        self.client.force_login(self.admin)
        self.client.post(reverse('review_signup', args=[application.pk]), {'action': 'approve'})
        application.refresh_from_db()
        self.assertFalse(is_teacher_account(application.user))
        self.assertFalse(application.user.is_staff)
        self.assertTrue(application.user.groups.filter(name='Accounts').exists())

    def test_invalid_signup_does_not_create_user(self):
        self.data['password2'] = 'different'
        response = self.client.post(reverse('signup'), self.data)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(SignupRequest.objects.exists())
        self.assertFalse(get_user_model().objects.filter(username='newteacher').exists())

    def test_login_dropdown_and_signup_link(self):
        response = self.client.get(reverse('login'))
        self.assertContains(response, '<select name="institution_id"')
        self.assertContains(response, '<select name="department"')
        self.assertContains(response, reverse('signup'))


class SignupScrollingTests(TestCase):
    """The sign-up form is taller than the card, so it must be scrollable.

    Regression tests for "scrolling does not work on /signup/": the form
    panel is absolutely positioned inside an ``overflow: hidden`` card.
    With only ``min-height: 100%`` the panel grew with its content, so
    ``overflow-y: auto`` never engaged and the form was clipped with no
    way to reach it; ``justify-content: center`` additionally pushed the
    top of an overflowing form above the scroll origin. On small screens
    the panel stayed absolute with ``overflow: visible``, so the page
    could not scroll to the clipped content either.
    """

    def _form_box_block(self, template):
        css = template.read_text(encoding='utf-8')
        return css.split('.form-box {', 1)[1].split('}', 1)[0]

    def _mobile_block(self, template):
        css = template.read_text(encoding='utf-8')
        return css.split('@media (max-width: 720px)', 1)[1].split('@media', 1)[0]

    def test_signup_form_panel_has_a_fixed_height_so_it_can_scroll(self):
        block = self._form_box_block(TEMPLATES / 'signup.html')
        self.assertIn('height: 100%', block)
        self.assertIn('max-height: 100%', block)
        self.assertIn('overflow-y: auto', block)
        self.assertNotIn('min-height: 100%', block)

    def test_signup_form_panel_is_not_centered_so_its_top_is_reachable(self):
        block = self._form_box_block(TEMPLATES / 'signup.html')
        self.assertNotIn('justify-content: center', block)
        self.assertIn('justify-content: flex-start', block)
        # Short panels stay vertically centered via auto margins, which
        # collapse to 0 when the content is taller than the panel.
        css = (TEMPLATES / 'signup.html').read_text(encoding='utf-8')
        self.assertIn('.form-box > :first-child { margin-top: auto; }', css)
        self.assertIn('.form-box > :last-child { margin-bottom: auto; }', css)

    def test_signup_form_scrolls_the_page_on_small_screens(self):
        mobile = self._mobile_block(TEMPLATES / 'signup.html')
        self.assertIn('position: relative', mobile)
        self.assertIn('height: auto', mobile)
        self.assertIn('.card { min-height: 0; }', mobile)

    def test_login_form_panel_has_the_same_scroll_contract(self):
        block = self._form_box_block(LOGIN_TEMPLATE)
        self.assertIn('height: 100%', block)
        self.assertIn('overflow-y: auto', block)
        self.assertNotIn('justify-content: center', block)
        mobile = self._mobile_block(LOGIN_TEMPLATE)
        self.assertIn('position: relative', mobile)
        self.assertIn('.card { min-height: 0; }', mobile)
