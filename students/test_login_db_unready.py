"""Regression test for the "login page shows HTTP 500" incident.

When the database has not been migrated (a fresh/reset Postgres on Render where
`manage.py migrate` never ran), reading the Institution table raises. The login
view must degrade to a clear, self-explanatory page instead of an opaque 500.
"""
from unittest import mock

from django.db.utils import ProgrammingError
from django.test import TestCase
from django.urls import reverse


class LoginDatabaseNotReadyTests(TestCase):
    def test_login_page_degrades_gracefully_when_institution_table_missing(self):
        # Simulate the missing-table error the way PostgreSQL raises it.
        with mock.patch(
            'students.views.Institution.objects.order_by',
            side_effect=ProgrammingError('relation "students_institution" does not exist'),
        ):
            response = self.client.get(reverse('login'))

        # Not a 500: a deliberate, retryable status with a helpful banner.
        self.assertEqual(response.status_code, 503)
        self.assertContains(
            response,
            'database has not been initialised',
            status_code=503,
        )

    def test_login_page_is_healthy_when_database_is_migrated(self):
        response = self.client.get(reverse('login'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'database has not been initialised')
