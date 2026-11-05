"""Tests for ``students/preflight.py`` and the ``production_preflight`` command.

The preflight exists because the dangerous production misconfigurations all
*boot fine*: DEBUG on, ALLOWED_HOSTS='*', local media disk, no backup, missing
static manifest. Each of those has a test here so the checklist itself cannot
rot.
"""
import io
from unittest import mock

from django.core.management import call_command
from django.test import SimpleTestCase, override_settings

from students import preflight


def good(**overrides):
    """A healthy production environment; override one value per test."""
    values = dict(
        debug=False,
        secret_key='x' * 60,
        allowed_hosts=['school.example.com'],
        csrf_trusted_origins=['https://school.example.com'],
        db_engine='django.db.backends.postgresql',
        media_backend='s3',
        newest_backup_age_hours=3.0,
        static_manifest_present=True,
        pg_dump_available=True,
        rate_limit_cache='db',
    )
    values.update(overrides)
    return preflight.evaluate_checks(**values)


def by_key(checks, key):
    return next(c for c in checks if c.key == key)


class PreflightEvaluationTests(SimpleTestCase):
    def test_healthy_environment_has_no_fail_and_no_warn(self):
        checks = good()
        self.assertEqual([c.key for c in checks if c.status != preflight.OK], [])

    def test_debug_true_is_a_hard_failure(self):
        self.assertEqual(by_key(good(debug=True), 'debug').status, preflight.FAIL)

    def test_default_django_secret_key_is_a_hard_failure(self):
        check = by_key(good(secret_key='django-insecure-abc123'), 'secret_key')
        self.assertEqual(check.status, preflight.FAIL)

    def test_short_secret_key_is_a_hard_failure(self):
        self.assertEqual(by_key(good(secret_key='short'), 'secret_key').status,
                         preflight.FAIL)

    def test_wildcard_allowed_hosts_is_a_hard_failure(self):
        self.assertEqual(by_key(good(allowed_hosts=['*']), 'allowed_hosts').status,
                         preflight.FAIL)

    def test_empty_allowed_hosts_is_a_hard_failure(self):
        self.assertEqual(by_key(good(allowed_hosts=[]), 'allowed_hosts').status,
                         preflight.FAIL)

    def test_missing_csrf_origins_is_only_a_warning(self):
        self.assertEqual(by_key(good(csrf_trusted_origins=[]), 'csrf_origins').status,
                         preflight.WARN)

    def test_sqlite_is_a_warning_not_a_failure(self):
        checks = good(db_engine='django.db.backends.sqlite3')
        self.assertEqual(by_key(checks, 'db_engine').status, preflight.WARN)
        # pg_dump is irrelevant on SQLite, so it must not fail there.
        self.assertEqual(by_key(checks, 'pg_dump').status, preflight.OK)

    def test_postgres_without_pg_dump_fails(self):
        self.assertEqual(by_key(good(pg_dump_available=False), 'pg_dump').status,
                         preflight.FAIL)

    def test_local_media_disk_is_a_warning(self):
        self.assertEqual(by_key(good(media_backend='filesystem'), 'media_backend').status,
                         preflight.WARN)

    def test_no_backup_at_all_fails(self):
        self.assertEqual(by_key(good(newest_backup_age_hours=None), 'backup_age').status,
                         preflight.FAIL)

    def test_stale_backup_warns(self):
        check = by_key(good(newest_backup_age_hours=preflight.BACKUP_STALE_HOURS + 1),
                       'backup_age')
        self.assertEqual(check.status, preflight.WARN)

    def test_missing_static_manifest_fails_when_debug_is_off(self):
        self.assertEqual(
            by_key(good(static_manifest_present=False), 'static_manifest').status,
            preflight.FAIL,
        )

    def test_missing_static_manifest_is_irrelevant_in_development(self):
        self.assertEqual(
            by_key(good(debug=True, static_manifest_present=False), 'static_manifest').status,
            preflight.OK,
        )

    def test_locmem_rate_limit_cache_warns(self):
        self.assertEqual(by_key(good(rate_limit_cache='locmem'), 'rate_limit_cache').status,
                         preflight.WARN)


class PreflightCommandTests(SimpleTestCase):
    """The command must exit non-zero when something is actually broken."""

    def _run(self, env):
        out = io.StringIO()
        with mock.patch.object(preflight, 'collect_environment', return_value=env):
            call_command('production_preflight', '--no-color', stdout=out)
        return out.getvalue()

    def test_exits_zero_on_healthy_environment(self):
        env = dict(
            debug=False, secret_key='x' * 60, allowed_hosts=['school.example.com'],
            csrf_trusted_origins=['https://school.example.com'],
            db_engine='django.db.backends.postgresql', media_backend='s3',
            newest_backup_age_hours=1.0, static_manifest_present=True,
            pg_dump_available=True, rate_limit_cache='db',
        )
        output = self._run(env)
        self.assertIn('লাইভে যাওয়ার জন্য প্রস্তুত', output)

    def test_exits_one_when_a_hard_requirement_fails(self):
        env = dict(
            debug=True, secret_key='django-insecure-abc', allowed_hosts=['*'],
            csrf_trusted_origins=[], db_engine='django.db.backends.postgresql',
            media_backend='filesystem', newest_backup_age_hours=None,
            static_manifest_present=False, pg_dump_available=False,
            rate_limit_cache='locmem',
        )
        with self.assertRaises(SystemExit) as ctx:
            self._run(env)
        self.assertEqual(ctx.exception.code, 1)

    def test_warnings_alone_do_not_block_by_default(self):
        env = dict(
            debug=False, secret_key='x' * 60, allowed_hosts=['school.example.com'],
            csrf_trusted_origins=['https://school.example.com'],
            db_engine='django.db.backends.postgresql', media_backend='filesystem',
            newest_backup_age_hours=1.0, static_manifest_present=True,
            pg_dump_available=True, rate_limit_cache='locmem',
        )
        output = self._run(env)
        self.assertIn('কোনো কঠিন সমস্যা নেই', output)


class BackupAgeTests(SimpleTestCase):
    def test_missing_root_returns_none(self):
        self.assertIsNone(preflight.newest_backup_age_hours('/nonexistent/lab-path'))

    def test_empty_root_returns_none(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(preflight.newest_backup_age_hours(tmp))

    def test_recent_folder_is_fresh(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            age = preflight.newest_backup_age_hours(tmp)
            self.assertIsNone(age)          # empty dir → no backup
            import os
            os.makedirs(os.path.join(tmp, 'backup-20260101T000000Z'))
            age = preflight.newest_backup_age_hours(tmp)
            self.assertIsNotNone(age)
            self.assertLess(age, 1.0)       # just created


@override_settings(DEBUG=True)
class HealthIntegrationSmokeTests(SimpleTestCase):
    """The URL is wired up in the project, not only the view."""

    def test_healthz_is_routable(self):
        from django.urls import reverse
        self.assertEqual(reverse('healthz'), '/healthz/')
