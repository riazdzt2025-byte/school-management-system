"""
Django settings for school_system project.
"""
from dotenv import load_dotenv
load_dotenv()

import os
from pathlib import Path
import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

# SECRET_KEY: previously hardcoded in this file and committed to a public repo,
# so it has been rotated. Set a SECRET_KEY environment variable in production
# (e.g. Render > Environment) to override this fallback.
SECRET_KEY = os.environ.get(
    'SECRET_KEY',
    'django-insecure-Px=l@@UFK#iOpiH$2K5z!EkskBj_3%kpy!2)_kS-qRoF90+DuP',
)

# DEBUG: defaults to True to match previous behaviour for local development.
# Set DEBUG=False as an environment variable in production.
DEBUG = os.environ.get('DEBUG', 'True') == 'True'

# Production hardening — only activates when DEBUG=False. Development / preview
# stays unchanged (DEBUG=True allows ALLOWED_HOSTS=['*'], no SSL redirect).
if not DEBUG:
    # These must be confirmed with a real HTTPS endpoint before raising HSTS
    # to a high value; 3600 is a safe starting point that can be increased.
    SECURE_HSTS_SECONDS = 3600
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    # The default fallback SECRET_KEY must never be used in production.
    if SECRET_KEY.startswith('django-insecure-'):
        from django.core.exceptions import ImproperlyConfigured
        raise ImproperlyConfigured(
            "SECRET_KEY is using the default fallback. Set a real SECRET_KEY environment "
            "variable before running with DEBUG=False (production)."
        )

# ALLOWED_HOSTS: comma-separated list via env var, e.g. "myapp.onrender.com,mydomain.com"
_allowed_hosts = os.environ.get('ALLOWED_HOSTS', '')
ALLOWED_HOSTS = [h.strip() for h in _allowed_hosts.split(',') if h.strip()] or ['*']
# CSRF_TRUSTED_ORIGINS: comma-separated origins including scheme,
# e.g. "https://myapp.onrender.com,https://*.e2b.app"
_csrf_origins = os.environ.get('CSRF_TRUSTED_ORIGINS', '')
CSRF_TRUSTED_ORIGINS = [o.strip() for o in _csrf_origins.split(',') if o.strip()]

# HTTPS behind a reverse proxy (Render, Nginx, Caddy).
#
# The proxy terminates TLS and forwards the request to Django over plain http.
# Django then sees an http origin for a POST that came from an https page, and
# the CSRF check fails with "Origin checking failed" (a 403 on login) while
# redirects are built with the wrong scheme. Opting in with
# TRUST_FORWARDED_PROTO=True makes Django read the proxy's
# X-Forwarded-Proto header instead of the connection.
#
# Both flags stay off by default: trusting these headers on a directly exposed
# port would let a client spoof the scheme/host. On Render set
# TRUST_FORWARDED_PROTO=True (and USE_X_FORWARDED_HOST=True so absolute URLs
# use the public hostname).
_TRUST_FORWARDED_PROTO = os.environ.get('TRUST_FORWARDED_PROTO', 'False') == 'True'
USE_X_FORWARDED_HOST = os.environ.get('USE_X_FORWARDED_HOST', 'False') == 'True'
if _TRUST_FORWARDED_PROTO:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    # Safe only because the scheme is now known to be https at the proxy.
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_SAMESITE = 'Lax'

LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'dashboard'
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'students',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'school_system.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'school_system' / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'students.context_processors.school_info',
            ],
        },
    },
]

WSGI_APPLICATION = 'school_system.wsgi.application'

# Database
DATABASES = {
    'default': dj_database_url.config(
        default=f'sqlite:///{BASE_DIR / "db.sqlite3"}',
        conn_max_age=600,
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'


# ---------------------------------------------------------------------------
# Media (student photos, imported spreadsheets) — must survive a redeploy (D-7)
# ---------------------------------------------------------------------------
# Render's free tier has no persistent disk: the container filesystem, and so
# BASE_DIR/media, is wiped on every deploy and every restart. Uploads written
# there vanish — the student keeps the record but loses the photo. The fix is
# S3-compatible object storage (Cloudflare R2, Backblaze B2, AWS S3, Wasabi,
# a MinIO box...) behind django-storages.
#
# It is opt-in through env, so local development and the preview keep the plain
# filesystem they have always had:
#
#   USE_S3=True   → media is written to the bucket; URLs come from that bucket
#   unset/false   → FileSystemStorage under MEDIA_ROOT (previous behaviour)
#
# Static files are deliberately untouched: they are baked into the build image
# and served by whitenoise, which is correct and costs nothing per request.
def _env_flag(name, env=None, default=False):
    """Read a boolean-ish environment variable ('True'/'1'/'yes'/'on')."""
    raw = (os.environ if env is None else env).get(name)
    if raw is None or raw.strip() == '':
        return default
    return raw.strip().lower() in ('1', 'true', 'yes', 'on')


def media_storage_config(env=None):
    """Resolve where uploaded media is stored, from `env` (default: os.environ).

    Returns ``{'backend': 'filesystem'}`` when S3 is off, else a dict with the
    bucket, credentials, endpoint, key prefix and (optional) public base URL.

    A half-configured bucket must not boot: with the filesystem fallback it
    would keep writing photos to a disk that gets wiped, which is exactly the
    bug this block exists to fix. So missing pieces raise immediately, the same
    way the default SECRET_KEY does above.
    """
    env = os.environ if env is None else env
    if not _env_flag('USE_S3', env):
        return {'backend': 'filesystem'}

    def _get(name, fallback=''):
        return (env.get(name) or fallback).strip()

    bucket = _get('AWS_STORAGE_BUCKET_NAME')
    access_key = _get('AWS_ACCESS_KEY_ID')
    secret_key = _get('AWS_SECRET_ACCESS_KEY')
    missing = [
        name for name, value in (
            ('AWS_STORAGE_BUCKET_NAME', bucket),
            ('AWS_ACCESS_KEY_ID', access_key),
            ('AWS_SECRET_ACCESS_KEY', secret_key),
        ) if not value
    ]
    if missing:
        from django.core.exceptions import ImproperlyConfigured
        raise ImproperlyConfigured(
            "USE_S3 is set but these are missing: " + ", ".join(missing)
            + ". Set all three, or unset USE_S3 to keep local file uploads. "
              "See docs/FREE_TIER_MEDIA_STORAGE.md."
        )

    return {
        'backend': 's3',
        'bucket': bucket,
        'access_key': access_key,
        'secret_key': secret_key,
        # R2 wants 'auto'; AWS S3 wants the real region name. Left unset,
        # boto3's own default applies — which is what AWS users want and why
        # 'auto' is NOT the fallback here.
        'region': _get('AWS_S3_REGION_NAME') or None,
        # Unset for real AWS; https://<account>.r2.cloudflarestorage.com for R2.
        'endpoint_url': _get('AWS_S3_ENDPOINT_URL') or None,
        # Key prefix inside the bucket, so one bucket can hold several apps.
        # An explicitly empty AWS_LOCATION means "no prefix" (files at the
        # bucket root), so it must not fall back to 'media'.
        'location': (
            env.get('AWS_LOCATION', 'media').strip().strip('/')
            if 'AWS_LOCATION' in env else 'media'
        ),
        # Set this to serve files publicly (CDN / public bucket). Left unset,
        # the bucket stays private and `photo.url` is a signed URL instead.
        'public_base_url': _get('AWS_S3_PUBLIC_BASE_URL') or None,
        # Object ACL: 'public-read' only makes sense for a bucket meant to be
        # public; private + signed URLs is the safer default for photos of
        # students (PII).
        'default_acl': _get('AWS_DEFAULT_ACL') or None,
        'cache_control': _get('AWS_S3_CACHE_CONTROL', 'max-age=2592000, public'),
        # Signed media URLs must outlive a school day of open tabs/printing.
        'querystring_expire': int(_get('AWS_S3_QUERYSTRING_EXPIRE', '86400')),
    }


def media_public_url(config, env=None):
    """The URL prefix media files are served from, matching `config`.

    For S3 the app can no longer serve `/media/` itself (Django is not a file
    server and `static()` only maps the local disk), so this has to be an
    absolute URL on the bucket/CDN.
    """
    env = os.environ if env is None else env
    # An explicit MEDIA_URL always wins — that is how a CDN with its own
    # domain, or a proxy path, is plugged in without touching code.
    override = (env.get('MEDIA_URL') or '').strip()
    if config['backend'] == 'filesystem':
        return override or '/media/'
    if override:
        return override
    prefix = config['location']
    if config['public_base_url']:
        base = config['public_base_url'].rstrip('/')
        return f"{base}/{prefix}/" if prefix else f"{base}/"
    if config['endpoint_url']:
        # Path-style addressing, which is what R2/B2/MinIO expect.
        base = config['endpoint_url'].rstrip('/')
        return f"{base}/{config['bucket']}/{prefix}/" if prefix else f"{base}/{config['bucket']}/"
    base = f"https://{config['bucket']}.s3.amazonaws.com"
    return f"{base}/{prefix}/" if prefix else f"{base}/"


MEDIA_CONFIG = media_storage_config()
MEDIA_BACKEND = MEDIA_CONFIG['backend']
MEDIA_IS_REMOTE = MEDIA_BACKEND == 's3'

MEDIA_URL = media_public_url(MEDIA_CONFIG)
# MEDIA_ROOT is configurable via env so production can point it at a persistent
# disk (Render) or an object-storage mount. It is unused when media goes to a
# bucket, but the backup tooling still reads it, and the local default keeps
# development working with no setup at all.
MEDIA_ROOT = Path(os.environ.get('MEDIA_ROOT', str(BASE_DIR / 'media')))

if MEDIA_IS_REMOTE:
    AWS_ACCESS_KEY_ID = MEDIA_CONFIG['access_key']
    AWS_SECRET_ACCESS_KEY = MEDIA_CONFIG['secret_key']
    AWS_STORAGE_BUCKET_NAME = MEDIA_CONFIG['bucket']
    # None means 'let boto3 decide' (the AWS path); R2/B2 want an
    # explicit value, e.g. AWS_S3_REGION_NAME=auto.
    AWS_S3_REGION_NAME = MEDIA_CONFIG['region']
    AWS_S3_ENDPOINT_URL = MEDIA_CONFIG['endpoint_url']
    AWS_S3_SIGNATURE_VERSION = 's3v4'
    # Third-party endpoints (R2, B2, MinIO) need path-style addressing; AWS
    # ignores this because it accepts both styles for virtual-host buckets.
    AWS_S3_ADDRESSING_STYLE = os.environ.get('AWS_S3_ADDRESSING_STYLE', 'path')
    AWS_LOCATION = MEDIA_CONFIG['location']
    AWS_S3_OBJECT_PARAMETERS = {'CacheControl': MEDIA_CONFIG['cache_control']}
    AWS_DEFAULT_ACL = MEDIA_CONFIG['default_acl']
    AWS_S3_FILE_OVERWRITE = False
    if MEDIA_CONFIG['public_base_url']:
        # Public bucket / CDN: hand storages the host so generated URLs match
        # MEDIA_URL, and skip signing (a public object needs no signature).
        from urllib.parse import urlsplit
        _split = urlsplit(MEDIA_CONFIG['public_base_url'])
        AWS_S3_CUSTOM_DOMAIN = _split.netloc or MEDIA_CONFIG['public_base_url'].rstrip('/')
        AWS_QUERYSTRING_AUTH = False
    else:
        # Private bucket: every photo is served through a signed URL.
        AWS_S3_CUSTOM_DOMAIN = None
        AWS_QUERYSTRING_AUTH = True
        AWS_QUERYSTRING_EXPIRE = MEDIA_CONFIG['querystring_expire']

# Manifest static storage hashes and verifies asset URLs — it needs
# `collectstatic` to have run, so it is only enabled when DEBUG is off.
# With it on in development (or under the test runner) every {% static %} tag
# raises "Missing staticfiles manifest entry" because no manifest exists yet.
STORAGES = {
    "default": {
        # django-storages 1.14 renamed S3Boto3Storage -> S3Storage (the old
        # path still resolves via storages.backends.s3boto3, but it is the
        # deprecated alias). Pinned in requirements.txt, so the new name is
        # what this build gets.
        "BACKEND": (
            "storages.backends.s3.S3Storage"
            if MEDIA_IS_REMOTE
            else "django.core.files.storage.FileSystemStorage"
        ),
    },
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        ),
    },
}

MAILERS = {
    'default': {
        'BACKEND': 'django.core.mail.backends.console.EmailBackend',
    },
}

# NCTB/SSC reading of an un-entered subject: a candidate who did not sit an
# assigned subject has not passed it, so that subject is graded F and the
# result becomes Fail (GPA 0.00). Set EXAM_ABSENT_SUBJECT_FAILS=False to ignore
# un-entered subjects instead — they then print a dash and stay out of the
# total. See RESULT_PUBLISHING_GUIDE.md.
EXAM_ABSENT_SUBJECT_FAILS = os.environ.get('EXAM_ABSENT_SUBJECT_FAILS', 'True') == 'True'

SCHOOL_INFO = {
    'name': 'Principal Kazi Faruky School And College',
    'address': 'Rakhalia, Raipur, Lakshmipur',
    'phone': '+880 1234-567890',
}