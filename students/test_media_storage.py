"""Free-tier media storage (D-7) — uploads must not live on the disk that a
Render deploy wipes.

Two halves:

* The settings helpers are pure functions over an env mapping, so the bucket
  decision (including "USE_S3 but you forgot the keys") is testable without
  touching ``os.environ`` or re-importing settings.
* The real ``S3Boto3Storage`` wiring is exercised only when ``django-storages``
  and ``boto3`` are importable. CI and the Render build install them from
  requirements.txt; a sandbox that skipped that step skips these tests instead
  of failing — the config above still holds either way.
"""
import importlib.util
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest import mock

from django.core.checks.registry import registry
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from students.management.commands.copy_media_to_storage import iter_media_files

from school_system import settings as project_settings
from students import checks

_HAS_S3_STACK = (
    importlib.util.find_spec('storages') is not None
    and importlib.util.find_spec('boto3') is not None
)
needs_s3_stack = unittest.skipUnless(
    _HAS_S3_STACK, "django-storages / boto3 not installed in this environment"
)

# A Cloudflare-R2-shaped config: third-party endpoint, path-style, 'auto' region.
R2_ENV = {
    'USE_S3': 'True',
    'AWS_STORAGE_BUCKET_NAME': 'school-media',
    'AWS_ACCESS_KEY_ID': 'AKIAIOSFODNN7EXAMPLE',
    'AWS_SECRET_ACCESS_KEY': 'secret-key-value',
    'AWS_S3_ENDPOINT_URL': 'https://acct123.r2.cloudflarestorage.com',
    'AWS_S3_REGION_NAME': 'auto',
    'AWS_LOCATION': 'media/',
}


class MediaBackendSelectionTests(TestCase):
    def test_defaults_to_filesystem_when_unset(self):
        self.assertEqual(project_settings.media_storage_config({}), {'backend': 'filesystem'})

    def test_falsy_values_keep_the_filesystem(self):
        for value in ('False', 'false', '0', 'no', '', '  '):
            with self.subTest(USE_S3=value):
                cfg = project_settings.media_storage_config({'USE_S3': value})
                self.assertEqual(cfg['backend'], 'filesystem')

    def test_any_common_truthy_spelling_enables_s3(self):
        for value in ('True', 'true', '1', 'yes', 'ON'):
            with self.subTest(USE_S3=value):
                cfg = project_settings.media_storage_config({**R2_ENV, 'USE_S3': value})
                self.assertEqual(cfg['backend'], 's3')

    def test_bucket_credentials_and_prefix_are_normalised(self):
        cfg = project_settings.media_storage_config(R2_ENV)
        self.assertEqual(cfg['bucket'], 'school-media')
        self.assertEqual(cfg['access_key'], 'AKIAIOSFODNN7EXAMPLE')
        self.assertEqual(cfg['region'], 'auto')
        self.assertEqual(cfg['endpoint_url'], 'https://acct123.r2.cloudflarestorage.com')
        # Trailing slash in AWS_LOCATION must not reach the key prefix.
        self.assertEqual(cfg['location'], 'media')
        # Defaults an operator should not have to think about.
        self.assertIsNone(cfg['public_base_url'])
        self.assertIsNone(cfg['default_acl'])
        self.assertEqual(cfg['querystring_expire'], 86400)

    def test_aws_s3_needs_no_endpoint_and_no_invented_region(self):
        cfg = project_settings.media_storage_config({
            'USE_S3': 'True',
            'AWS_STORAGE_BUCKET_NAME': 'b',
            'AWS_ACCESS_KEY_ID': 'a',
            'AWS_SECRET_ACCESS_KEY': 's',
        })
        self.assertIsNone(cfg['endpoint_url'])
        # 'auto' is an R2 thing; forcing it on AWS S3 breaks signing.
        self.assertIsNone(cfg['region'])

    def test_incomplete_config_names_every_missing_variable(self):
        env = {
            'USE_S3': 'True',
            'AWS_STORAGE_BUCKET_NAME': 'school-media',
            'AWS_SECRET_ACCESS_KEY': 'secret-key-value',
        }
        with self.assertRaises(ImproperlyConfigured) as cm:
            project_settings.media_storage_config(env)
        message = str(cm.exception)
        self.assertIn('AWS_ACCESS_KEY_ID', message)
        # The key that IS set must not be reported as missing.
        self.assertNotIn('AWS_SECRET_ACCESS_KEY, ', message)
        self.assertIn('docs/FREE_TIER_MEDIA_STORAGE.md', message)

    def test_blank_values_count_as_missing(self):
        env = {**R2_ENV, 'AWS_ACCESS_KEY_ID': '   '}
        with self.assertRaises(ImproperlyConfigured) as cm:
            project_settings.media_storage_config(env)
        self.assertIn('AWS_ACCESS_KEY_ID', str(cm.exception))


class MediaUrlTests(TestCase):
    def test_filesystem_serves_media_from_the_app(self):
        self.assertEqual(project_settings.media_public_url({'backend': 'filesystem'}, {}), '/media/')

    def test_bucket_endpoint_url_is_path_style(self):
        cfg = project_settings.media_storage_config(R2_ENV)
        self.assertEqual(
            project_settings.media_public_url(cfg, {}),
            'https://acct123.r2.cloudflarestorage.com/school-media/media/',
        )

    def test_public_base_url_wins_over_endpoint_guessing(self):
        cfg = project_settings.media_storage_config({
            **R2_ENV, 'AWS_S3_PUBLIC_BASE_URL': 'https://cdn.example.com/school/',
        })
        self.assertEqual(
            project_settings.media_public_url(cfg, {}),
            'https://cdn.example.com/school/media/',
        )

    def test_empty_location_does_not_leave_a_trailing_slash_pair(self):
        cfg = project_settings.media_storage_config({**R2_ENV, 'AWS_LOCATION': ''})
        self.assertEqual(
            project_settings.media_public_url(cfg, {}),
            'https://acct123.r2.cloudflarestorage.com/school-media/',
        )

    def test_plain_aws_s3_url(self):
        cfg = project_settings.media_storage_config({
            'USE_S3': 'True',
            'AWS_STORAGE_BUCKET_NAME': 'school-media',
            'AWS_ACCESS_KEY_ID': 'a',
            'AWS_SECRET_ACCESS_KEY': 's',
            'AWS_LOCATION': 'media',
        })
        self.assertEqual(
            project_settings.media_public_url(cfg, {}),
            'https://school-media.s3.amazonaws.com/media/',
        )

    def test_explicit_media_url_always_wins(self):
        cfg = project_settings.media_storage_config(R2_ENV)
        self.assertEqual(
            project_settings.media_public_url(cfg, {'MEDIA_URL': 'https://files.example.com/uploads/'}),
            'https://files.example.com/uploads/',
        )


class MediaStorageCheckTests(TestCase):
    """The check that keeps a silent data-loss configuration from shipping."""

    def test_production_media_on_the_app_disk_warns(self):
        ephemeral = str(Path(project_settings.BASE_DIR) / 'media')
        with override_settings(DEBUG=False, MEDIA_IS_REMOTE=False, MEDIA_ROOT=ephemeral):
            ids = [c.id for c in checks.check_media_storage_durable()]
        self.assertIn('students.W010', ids)

    def test_persistent_mount_is_silent(self):
        with override_settings(DEBUG=False, MEDIA_IS_REMOTE=False, MEDIA_ROOT='/data/media'):
            ids = [c.id for c in checks.check_media_storage_durable()]
        self.assertEqual(ids, [])

    def test_development_is_silent(self):
        ephemeral = str(Path(project_settings.BASE_DIR) / 'media')
        with override_settings(DEBUG=True, MEDIA_IS_REMOTE=False, MEDIA_ROOT=ephemeral):
            ids = [c.id for c in checks.check_media_storage_durable()]
        self.assertEqual(ids, [])

    def test_remote_media_is_not_flagged_as_ephemeral(self):
        # MEDIA_ROOT still exists when media goes to a bucket; the check must
        # not warn about the disk nobody is writing to.
        ephemeral = str(Path(project_settings.BASE_DIR) / 'media')
        with override_settings(DEBUG=False, MEDIA_IS_REMOTE=True, MEDIA_ROOT=ephemeral):
            ids = [c.id for c in checks.check_media_storage_durable()]
        self.assertEqual(ids, [])

    def test_the_ephemeral_warning_is_deploy_only(self):
        """Plain `manage.py check` (and the test runner) must stay silent.

        The deploy tag is what keeps this from becoming the warning everyone
        learns to ignore; CI and Render are told to run `check --deploy`.
        """
        self.assertIn(
            checks.check_media_storage_durable, registry.deployment_checks,
            "W010 should only run under `manage.py check --deploy`",
        )
        self.assertIn(
            checks.check_s3_dependencies, registry.registered_checks,
            "the dependency error must run on every check, deploy or not",
        )


class S3DependencyCheckTests(TestCase):
    def test_noop_when_media_is_local(self):
        with override_settings(MEDIA_IS_REMOTE=False):
            self.assertEqual(checks.check_s3_dependencies(), [])

    def test_satisfied_when_both_packages_import(self):
        # This is the CI / Render case: requirements.txt installs both.
        with override_settings(MEDIA_IS_REMOTE=True):
            self.assertEqual(checks.check_s3_dependencies(), [])

    def test_error_per_missing_package(self):
        with override_settings(MEDIA_IS_REMOTE=True), \
                mock.patch.object(checks, '_module_available', return_value=False):
            errors = checks.check_s3_dependencies()
        self.assertEqual([e.id for e in errors], ['students.E011', 'students.E011'])
        self.assertIn('storages', str(errors[0]))


@needs_s3_stack
class S3BackendWiringTests(TestCase):
    """Only runs where django-storages + boto3 are installed (CI, Render)."""

    def _s3_override(self, **extra):
        cfg = project_settings.media_storage_config(R2_ENV)
        base = dict(
            STORAGES={
                'default': {'BACKEND': 'storages.backends.s3.S3Storage'},
                'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
            },
            MEDIA_URL=project_settings.media_public_url(cfg, {}),
            AWS_ACCESS_KEY_ID=cfg['access_key'],
            AWS_SECRET_ACCESS_KEY=cfg['secret_key'],
            AWS_STORAGE_BUCKET_NAME=cfg['bucket'],
            AWS_S3_REGION_NAME=cfg['region'],
            AWS_S3_ENDPOINT_URL=cfg['endpoint_url'],
            AWS_S3_ADDRESSING_STYLE='path',
            AWS_S3_SIGNATURE_VERSION='s3v4',
            AWS_LOCATION=cfg['location'],
            AWS_DEFAULT_ACL=None,
            AWS_S3_FILE_OVERWRITE=False,
            AWS_S3_CUSTOM_DOMAIN=None,
            AWS_QUERYSTRING_AUTH=True,
            AWS_QUERYSTRING_EXPIRE=cfg['querystring_expire'],
        )
        # A merged dict, not dict(..., **extra): dict() rejects the duplicate
        # key a caller passes when overriding one of the defaults above.
        return {**base, **extra}

    def test_default_storage_becomes_the_s3_backend(self):
        from django.core.files.storage import default_storage
        from storages.backends.s3 import S3Storage

        with override_settings(**self._s3_override()):
            self.assertIsInstance(default_storage, S3Storage)
            # Private bucket by default: photos of students are not world-readable.
            self.assertTrue(default_storage.querystring_auth)
            self.assertEqual(default_storage.location, 'media')

    def test_private_bucket_urls_are_absolute_and_prefixed(self):
        from django.core.files.storage import default_storage

        with override_settings(**self._s3_override()):
            url = default_storage.url('student_photos/123.jpg')
        self.assertTrue(url.startswith('https://'), url)
        self.assertIn('acct123.r2.cloudflarestorage.com', url)
        self.assertIn('media/student_photos/123.jpg', url)

    def test_public_base_turns_signing_off_and_uses_the_cdn_host(self):
        from django.core.files.storage import default_storage

        public = 'https://cdn.example.com'
        with override_settings(**self._s3_override(
            AWS_S3_CUSTOM_DOMAIN='cdn.example.com',
            AWS_QUERYSTRING_AUTH=False,
            MEDIA_URL=f"{public}/media/",
        )):
            url = default_storage.url('student_photos/123.jpg')
        self.assertEqual(url, f"{public}/media/student_photos/123.jpg")

    def test_student_photo_field_resolves_through_the_bucket(self):
        """The model field must follow the configured backend, not a cached
        filesystem storage — otherwise photos land in BASE_DIR/media again.

        ``upload_to='student_photos/'`` is resolved against ``default_storage``
        at access time, so the field's URL has to come out of the bucket.
        """
        from urllib.parse import urlsplit

        from students.models import Student

        with override_settings(**self._s3_override()):
            url = Student._meta.get_field('photo').storage.url('student_photos/x.jpg')
            parsed = urlsplit(url)

        self.assertEqual(parsed.scheme, 'https')
        self.assertEqual(parsed.netloc, 'acct123.r2.cloudflarestorage.com')
        # <bucket>/<AWS_LOCATION>/<upload_to>/<name>
        self.assertEqual(parsed.path, '/school-media/media/student_photos/x.jpg')
        # Private bucket by default, so the URL carries a signature.
        self.assertIn('X-Amz-Signature', parsed.query)


class CopyMediaToStorageTests(TestCase):
    """`manage.py copy_media_to_storage` — the one-way move of existing uploads.

    The 'bucket' here is a second FileSystemStorage pointed at a temp dir: the
    command only talks to the storage API, so this proves the key names and the
    idempotence without needing network access or the S3 packages at all.
    """

    def _storages(self, dest):
        return {
            'default': {
                'BACKEND': 'django.core.files.storage.FileSystemStorage',
                'OPTIONS': {'location': str(dest)},
            },
            'staticfiles': {
                'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
            },
        }

    def _make_sources(self, root):
        (root / 'student_photos').mkdir(parents=True)
        (root / 'student_photos' / '12.jpg').write_bytes(b'jpeg-bytes')
        (root / 'imports').mkdir()
        (root / 'imports' / 'marks.xlsx').write_bytes(b'xlsx')
        # A symlink must never be read: it is a read-anything primitive.
        (root / 'student_photos' / 'escape.png').symlink_to(Path('/etc/passwd'))
        # A bare directory is not a file.
        (root / 'empty_dir').mkdir()

    def test_refuses_when_media_is_still_local(self):
        with override_settings(MEDIA_IS_REMOTE=False):
            with self.assertRaises(CommandError) as cm:
                call_command('copy_media_to_storage', stdout=StringIO(), stderr=StringIO())
        self.assertIn('USE_S3=True', str(cm.exception))

    def test_copies_files_preserving_relative_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, dest = Path(tmp) / 'media', Path(tmp) / 'bucket'
            self._make_sources(src)
            with override_settings(MEDIA_IS_REMOTE=True, MEDIA_ROOT=str(src), STORAGES=self._storages(dest)):
                call_command('copy_media_to_storage', stdout=StringIO())
            self.assertEqual((dest / 'student_photos' / '12.jpg').read_bytes(), b'jpeg-bytes')
            self.assertEqual((dest / 'imports' / 'marks.xlsx').read_bytes(), b'xlsx')
            self.assertFalse((dest / 'student_photos' / 'escape.png').exists())
            self.assertFalse((dest / 'empty_dir').exists())
            # Source is left alone: this is a copy, not a move.
            self.assertTrue((src / 'student_photos' / '12.jpg').exists())

    def test_second_run_is_a_no_op(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, dest = Path(tmp) / 'media', Path(tmp) / 'bucket'
            self._make_sources(src)
            with override_settings(MEDIA_IS_REMOTE=True, MEDIA_ROOT=str(src), STORAGES=self._storages(dest)):
                call_command('copy_media_to_storage', stdout=StringIO())
                out = StringIO()
                call_command('copy_media_to_storage', stdout=out)
            self.assertIn('0 copied, 2 already present, 0 failed', out.getvalue())

    def test_stale_copy_is_replaced_under_the_same_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, dest = Path(tmp) / 'media', Path(tmp) / 'bucket'
            self._make_sources(src)
            with override_settings(MEDIA_IS_REMOTE=True, MEDIA_ROOT=str(src), STORAGES=self._storages(dest)):
                call_command('copy_media_to_storage', stdout=StringIO())
                # The bucket copy is now older/shorter than the local file.
                (dest / 'student_photos' / '12.jpg').write_bytes(b'stal')
                call_command('copy_media_to_storage', stdout=StringIO())
            self.assertEqual((dest / 'student_photos' / '12.jpg').read_bytes(), b'jpeg-bytes')
            # save() would have invented '12_<random>.jpg'; overwrite must not.
            self.assertEqual(sorted(p.name for p in (dest / 'student_photos').iterdir()), ['12.jpg'])

    def test_dry_run_writes_nothing_but_lists(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, dest = Path(tmp) / 'media', Path(tmp) / 'bucket'
            self._make_sources(src)
            with override_settings(MEDIA_IS_REMOTE=True, MEDIA_ROOT=str(src), STORAGES=self._storages(dest)):
                out = StringIO()
                call_command('copy_media_to_storage', dry_run=True, stdout=out)
            text = out.getvalue()
            self.assertIn('student_photos/12.jpg', text)
            self.assertIn('[dry run]', text)
            self.assertFalse(dest.exists())

    def test_missing_media_directory_is_not_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, dest = Path(tmp) / 'nothing-here', Path(tmp) / 'bucket'
            with override_settings(MEDIA_IS_REMOTE=True, MEDIA_ROOT=str(src), STORAGES=self._storages(dest)):
                out = StringIO()
                call_command('copy_media_to_storage', stdout=out)
        self.assertIn('nothing to do', out.getvalue())


class IterMediaFilesTests(TestCase):
    def test_absent_root_yields_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(list(iter_media_files(Path(tmp) / 'nope')), [])

    def test_only_regular_files_and_posix_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'media'
            (root / 'a' / 'b').mkdir(parents=True)
            (root / 'a' / 'b' / 'c.txt').write_bytes(b'x')
            found = list(iter_media_files(root))
            self.assertEqual([(p.relative_to(root).as_posix(), n) for p, n in found],
                             [('a/b/c.txt', 'a/b/c.txt')])
