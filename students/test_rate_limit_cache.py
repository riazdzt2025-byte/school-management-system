"""Tests for SEC-FU-1: where the rate-limit and lockout counters are stored.

Default (RATE_LIMIT_CACHE unset): per-process memory, behaviour unchanged.
RATE_LIMIT_CACHE=db: a database table shared by every worker and kept across
restarts. Both must give the same lockout behaviour, and a broken counter
store must never take the login page down.
"""
import os
import subprocess
import sys
from unittest import mock

from django.conf import settings
from django.core.cache import caches
from django.core.cache.backends.db import DatabaseCache
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from . import test_rate_limiting
from .models import RateLimitCacheEntry
from .views import _rate_limit_exceeded

DB_CACHES = {
    'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'},
    'ratelimit': {
        'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
        'LOCATION': 'django_cache',
        'OPTIONS': {'MAX_ENTRIES': 20000, 'CULL_FREQUENCY': 4},
    },
}


class RateLimitCacheSettingTests(TestCase):
    def test_default_counters_stay_in_process_memory(self):
        self.assertEqual(settings.RATE_LIMIT_CACHE, 'locmem')
        self.assertIn('LocMemCache', settings.CACHES['ratelimit']['BACKEND'])

    def test_cache_table_is_created_by_migrate(self):
        self.assertEqual(RateLimitCacheEntry.objects.count(), 0)

    def test_unknown_value_stops_startup_with_a_clear_message(self):
        env = dict(os.environ, RATE_LIMIT_CACHE='bogus', DJANGO_SETTINGS_MODULE='school_system.settings')
        result = subprocess.run(
            [sys.executable, '-c', 'import django; django.setup()'],
            cwd=settings.BASE_DIR, env=env, capture_output=True, text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('RATE_LIMIT_CACHE', result.stderr)


@override_settings(CACHES=DB_CACHES)
class RateLimitTestsOnDatabaseCache(test_rate_limiting.RateLimitTests):
    """The whole existing rate-limit suite again, with counters in the database."""


@override_settings(CACHES=DB_CACHES)
class DatabaseCounterStorageTests(TestCase):
    def setUp(self):
        caches['ratelimit'].clear()

    def test_failed_logins_are_stored_in_the_database_table(self):
        for _ in range(2):
            self.client.post(reverse('login'), {
                'username': 'nobody', 'password': 'wrong',
                'institution_id': 1, 'department': 'Office',
            })
        keys = list(RateLimitCacheEntry.objects.values_list('cache_key', flat=True))
        self.assertTrue(any('loginfail' in key for key in keys), keys)

    def test_another_worker_sees_the_same_counter(self):
        caches['ratelimit'].set('loginfail:203.0.113.9', 4, 60)
        other_worker = DatabaseCache('django_cache', {})
        self.assertEqual(other_worker.get('loginfail:203.0.113.9'), 4)


class CounterStoreFailureTests(TestCase):
    """If the counter store is down, requests go through and a warning is logged."""

    def test_login_page_still_answers_when_the_store_is_down(self):
        with mock.patch('students.views._rl_cache', side_effect=RuntimeError('store down')):
            with self.assertLogs('students.views', level='WARNING'):
                response = self.client.post(reverse('login'), {
                    'username': 'nobody', 'password': 'wrong',
                    'institution_id': 1, 'department': 'Office',
                })
        self.assertEqual(response.status_code, 200)

    def test_public_admission_is_not_blocked_when_the_store_is_down(self):
        request = RequestFactory().get('/admission/apply/')
        with mock.patch('students.views._rl_cache', side_effect=RuntimeError('store down')):
            with self.assertLogs('students.views', level='WARNING'):
                self.assertFalse(_rate_limit_exceeded(request, 'public_admission', 5, 600))
