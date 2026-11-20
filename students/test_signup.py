from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from .models import Employee, Institution, InstitutionAccess, SignupRequest
from .teacher_scope import is_teacher_account


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
        self.assertRedirects(response, reverse('dashboard'), fetch_redirect_response=False)

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
