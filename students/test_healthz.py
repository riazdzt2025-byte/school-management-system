"""Tests for the public health endpoint ``/healthz/``.

The endpoint is publicly reachable (Render's health check hits it), so these
tests pin the two properties that matter most:

1. it tells the truth about the database (200 vs 503), and
2. it leaks nothing — no exception text, no host names, no extra keys.
"""
from unittest import mock

from django.db import DatabaseError
from django.test import TestCase
from django.urls import reverse


class HealthEndpointTests(TestCase):
    def test_healthy_database_returns_200_and_ok_payload(self):
        response = self.client.get(reverse('healthz'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok', 'db': 'ok'})
        # A cached "ok" is worse than no check at all.
        self.assertEqual(response['Cache-Control'], 'no-store')

    def test_database_error_returns_503_without_leaking_details(self):
        secret_detail = 'password authentication failed for user "school_admin"'
        with mock.patch(
            'students.health.connections',
            {'default': mock.Mock(cursor=mock.Mock(side_effect=DatabaseError(secret_detail)))},
        ):
            response = self.client.get(reverse('healthz'))

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {'status': 'error', 'db': 'error'})
        self.assertNotIn('password', response.content.decode().lower())
        self.assertNotIn('authentication', response.content.decode().lower())

    def test_any_exception_is_reported_as_not_ready(self):
        # A connection error, not a DatabaseError: both must degrade to 503.
        with mock.patch(
            'students.health.connections',
            {'default': mock.Mock(cursor=mock.Mock(side_effect=OSError('network unreachable')))},
        ):
            response = self.client.get(reverse('healthz'))

        self.assertEqual(response.status_code, 503)
        self.assertNotIn('network', response.content.decode().lower())

    def test_endpoint_needs_no_login(self):
        # Never log in: the response must still be the real check, not a redirect.
        response = self.client.get(reverse('healthz'))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('Location', response)

    def test_state_changing_methods_are_refused(self):
        # A probe is read-only; accepting POST would widen the CSRF-exempt
        # surface for no benefit.
        self.assertEqual(self.client.post(reverse('healthz')).status_code, 405)

    def test_payload_has_exactly_two_keys(self):
        # Guards against someone "helpfully" adding the database name, version
        # or build id to a public endpoint.
        payload = self.client.get(reverse('healthz')).json()
        self.assertEqual(set(payload), {'status', 'db'})
