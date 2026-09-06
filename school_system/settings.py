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
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'
# Manifest static storage hashes and verifies asset URLs — it needs
# `collectstatic` to have run, so it is only enabled when DEBUG is off.
# With it on in development (or under the test runner) every {% static %} tag
# raises "Missing staticfiles manifest entry" because no manifest exists yet.
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
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

SCHOOL_INFO = {
    'name': 'Principal Kazi Faruky School And College',
    'address': 'Rakhalia, Raipur, Lakshmipur',
    'phone': '+880 1234-567890',
}