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
STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
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