"""The merged sign-in page (the single /login/ route).

The promise this file protects: **/login/ signs in exactly the people the
office screens serve — linked, active, teaching employees for the Teacher
department, and active InstitutionAccess rows for Office / Exam / Accounts —
and nobody else.** A bare Teacher access row whose employee link was removed
(or a resigned teacher) must not bounce between the dashboard and the teacher
home forever.
"""
from datetime import date

from django.contrib.auth import get_user_model
from django.core.cache import caches
from django.test import TestCase
from django.urls import reverse

from .models import Employee, Institution, InstitutionAccess
from .permissions import ensure_default_groups


class LoginPageTests(TestCase):
    def setUp(self):
        ensure_default_groups()
        caches['ratelimit'].clear()
        self.url = reverse('login')
        self.institution = Institution.objects.create(
            name='Teacher School', classes='9,10', number=4,
        )
        self.other_institution = Institution.objects.create(
            name='Elsewhere School', classes='9', number=5,
        )
        self.teacher_user = get_user_model().objects.create_user(
            username='teacher', password='password',
        )
        self.employee = Employee.objects.create(
            name='Teacher One', designation='Assistant Teacher',
            department='Science', institution=self.institution,
            join_date=date(2020, 1, 1), user=self.teacher_user,
        )

    def post(self, **data):
        payload = {
            'institution_id': str(self.institution.pk),
            'department': 'Teacher',
            'username': 'teacher',
            'password': 'password',
        }
        payload.update(data)
        return self.client.post(self.url, payload)

    # --- the page itself -------------------------------------------------

    def test_get_renders_the_trust_card_with_institution_and_department_choices(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('Welcome Back!', content)
        self.assertIn('Professor Kazi Faruky Kallan Trust', content)
        self.assertIn('<select name="institution_id"', content)
        self.assertIn('<select name="department"', content)
        self.assertIn(self.institution.name, content)
        self.assertIn(reverse('signup'), content)

    def test_no_separate_teacher_login_page_remains(self):
        # The teacher sign-in was merged into the single /login/ page; the
        # old /teacher-login/ route is gone.
        from django.urls import NoReverseMatch
        with self.assertRaises(NoReverseMatch):
            reverse('teacher_login')

    def test_authenticated_user_is_redirected_away(self):
        self.client.force_login(self.teacher_user)
        response = self.client.get(self.url)
        self.assertRedirects(response, reverse('dashboard'), fetch_redirect_response=False)

    # --- the happy path --------------------------------------------------

    def test_linked_teacher_is_signed_in_and_sent_to_the_classroom(self):
        response = self.post()
        self.assertRedirects(response, reverse('teacher_home'), fetch_redirect_response=False)
        session = self.client.session
        self.assertEqual(session['selected_department'], 'Teacher')
        self.assertEqual(session['selected_institution_id'], str(self.institution.pk))

    def test_first_sign_in_persists_the_teacher_access_row(self):
        self.assertFalse(
            InstitutionAccess.objects.filter(
                user=self.teacher_user, department='Teacher',
            ).exists()
        )
        self.post()
        self.assertTrue(
            InstitutionAccess.objects.filter(
                user=self.teacher_user,
                institution=self.institution,
                department='Teacher',
                is_active=True,
            ).exists()
        )

    def test_staff_sign_in_goes_to_the_dashboard(self):
        staff = get_user_model().objects.create_user(
            username='principal', password='password', is_staff=True,
        )
        response = self.post(username='principal', password='password')
        self.assertRedirects(response, reverse('dashboard'), fetch_redirect_response=False)

    # --- who is turned away ----------------------------------------------

    def test_wrong_password_is_refused_and_not_signed_in(self):
        response = self.post(password='wrong-password')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_unlinked_user_with_correct_password_is_refused(self):
        get_user_model().objects.create_user(username='ghost', password='password')
        response = self.post(username='ghost')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)
        self.assertContains(response, 'not linked to a teacher record')

    def test_teacher_of_another_institution_cannot_enter_this_one(self):
        response = self.post(institution_id=str(self.other_institution.pk))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_resigned_teacher_cannot_sign_in(self):
        self.employee.status = 'RESIGNED'
        self.employee.save(update_fields=['status'])
        response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_non_teaching_employee_cannot_sign_in(self):
        clerk_user = get_user_model().objects.create_user(
            username='clerk', password='password',
        )
        Employee.objects.create(
            name='Office Clerk', designation='Accountant',
            department='Accounts', institution=self.institution,
            join_date=date(2021, 1, 1), user=clerk_user,
        )
        response = self.post(username='clerk')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_revoked_teacher_access_is_not_silently_reactivated(self):
        InstitutionAccess.objects.create(
            user=self.teacher_user, institution=self.institution,
            department='Teacher', is_active=False,
        )
        response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)

    # --- lockout -----------------------------------------------------------

    def test_five_failed_attempts_lock_the_ip_out(self):
        for _ in range(5):
            self.post(password='wrong-password')
        response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Too many failed login attempts')
        self.assertNotIn('_auth_user_id', self.client.session)
