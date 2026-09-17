"""Tests for P1-9 (public admission rate limit) and P2-2 (login lockout).

The limits are per-IP counters in the Django cache, so tests clear the cache in
setUp to avoid cross-test leakage.
"""
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse


class RateLimitTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(
            username='alice', password='correct-password',
        )

    def test_public_admission_throttles_after_limit(self):
        url = reverse('public_admission_apply')
        # Minimal/invalid POST is enough — the throttle counts POSTs regardless
        # of form validity.
        payload = {'applicant_name': 'Throttled Applicant'}
        for _ in range(5):
            response = self.client.post(url, payload)
            self.assertTrue(
                'Too many submissions' not in response.content.decode(),
                msg='must not be throttled before the limit',
            )
        # The 6th request is throttled.
        response = self.client.post(url, payload)
        self.assertEqual(response.status_code, 200)
        self.assertIn('Too many submissions', response.content.decode())

    def test_login_locks_out_after_failed_attempts(self):
        url = reverse('login')
        bad = {'username': 'alice', 'password': 'wrong',
               'institution_id': '', 'department': 'Office'}
        for _ in range(5):
            response = self.client.post(url, bad)
            self.assertNotIn('Too many failed login attempts',
                             response.content.decode())
        # Even with the correct password, the 6th attempt is locked out.
        good = {'username': 'alice', 'password': 'correct-password',
                'institution_id': '', 'department': 'Office'}
        response = self.client.post(url, good)
        self.assertEqual(response.status_code, 200)
        self.assertIn('Too many failed login attempts', response.content.decode())

    def test_login_lockout_cannot_be_bypassed_by_spoofing_xff(self):
        """SEC batch-02: X-Forwarded-For is `client, proxy1, ...`; the spoofable
        entries are the client-controlled ones on the left. The right-most entry
        is appended by the closest trusted proxy and cannot be forged from the
        client, so the lockout must keep applying no matter how the left side
        of the header changes between requests."""
        url = reverse('login')
        bad = {'username': 'alice', 'password': 'wrong',
               'institution_id': '', 'department': 'Office'}
        fake_edge_ip = '203.0.113.10'
        for index in range(5):
            response = self.client.post(
                url, bad,
                HTTP_X_FORWARDED_FOR=f'10.0.0.{index}, 172.16.0.{index}, {fake_edge_ip}',
            )
            self.assertNotIn('Too many failed login attempts',
                             response.content.decode())
        # The 6th request, again with a fresh spoofed left side, is locked out.
        good = {'username': 'alice', 'password': 'correct-password',
                'institution_id': '', 'department': 'Office'}
        response = self.client.post(
            url, good,
            HTTP_X_FORWARDED_FOR=f'10.9.9.9, {fake_edge_ip}',
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('Too many failed login attempts', response.content.decode())

    def test_public_admission_throttle_cannot_be_bypassed_by_spoofing_xff(self):
        url = reverse('public_admission_apply')
        fake_edge_ip = '198.51.100.20'
        payload = {'applicant_name': 'Throttled Applicant'}
        for index in range(5):
            response = self.client.post(
                url, payload,
                HTTP_X_FORWARDED_FOR=f'192.0.2.{index}, {fake_edge_ip}',
            )
            self.assertNotIn('Too many submissions', response.content.decode())
        response = self.client.post(
            url, payload, HTTP_X_FORWARDED_FOR=f'192.0.2.99, {fake_edge_ip}',
        )
        self.assertIn('Too many submissions', response.content.decode())

    def test_client_ip_falls_back_to_remote_addr_without_xff(self):
        from django.test import RequestFactory
        from students.views import _client_ip
        request = RequestFactory().get('/', REMOTE_ADDR='192.0.2.77')
        self.assertEqual(_client_ip(request), '192.0.2.77')

    def test_client_ip_prefers_rightmost_xff_entry(self):
        from django.test import RequestFactory
        from students.views import _client_ip
        request = RequestFactory().get(
            '/', HTTP_X_FORWARDED_FOR=' 9.9.9.9 , , 203.0.113.5 ',
        )
        self.assertEqual(_client_ip(request), '203.0.113.5')

    def test_successful_login_resets_fail_counter(self):
        url = reverse('login')
        bad = {'username': 'alice', 'password': 'wrong',
               'institution_id': '', 'department': 'Office'}
        # Two failures, then a success -> counter resets.
        self.client.post(url, bad)
        self.client.post(url, bad)
        # The admin/staff path only logs in when an InstitutionAccess exists for
        # the chosen institution, so set up an active access row.
        from .models import Institution, InstitutionAccess
        inst = Institution.objects.create(name='School', classes='6,9')
        InstitutionAccess.objects.create(
            user=self.user, institution=inst, department='Office', is_active=True,
        )
        good = {'username': 'alice', 'password': 'correct-password',
                'institution_id': str(inst.pk), 'department': 'Office'}
        response = self.client.post(url, good)
        self.assertEqual(response.status_code, 302)
        # Counter reset means the next bad attempt is only failure #1, not #3.
        response = self.client.post(url, bad)
        self.assertNotIn('Too many failed login attempts', response.content.decode())
