"""Production preflight — the checklist that decides "can we go live?".

The migration to PostgreSQL + object storage + a daily backup touches three
things that fail *silently* when they are wrong:

* ``DEBUG=True`` in production shows tracebacks to every parent who visits.
* ``ALLOWED_HOSTS=['*']`` lets anyone point a hostname at the app.
* ``USE_S3`` off (or the static manifest missing) means photos and stylesheets
  disappear on the first redeploy — while every page still returns HTTP 200.
* No fresh backup means the first data-loss incident is also the last one.

None of these raise on boot, so they need to be *checked* before traffic
arrives. ``manage.py production_preflight`` runs this module and exits non-zero
when a hard requirement fails, which makes it usable in a deploy script or in
CI against a staging environment.

The logic lives here — separate from the management command — as a pure
function of explicit values, so it can be unit-tested without a live cloud
account. The tests are in ``students/test_production_preflight.py``.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings

OK = 'ok'
WARN = 'warn'
FAIL = 'fail'

#: A backup older than this is "stale": the daily cron should never let it happen.
BACKUP_STALE_HOURS = 48


@dataclass(frozen=True)
class Check:
    """One row of the preflight report."""

    key: str
    title: str
    status: str
    detail: str

    @property
    def ok(self) -> bool:
        return self.status == OK


def _is_insecure_secret(value: str) -> bool:
    return not value or value.startswith('django-insecure-') or len(value) < 50


def evaluate_checks(
    *,
    debug: bool,
    secret_key: str,
    allowed_hosts,
    csrf_trusted_origins,
    db_engine: str,
    media_backend: str,
    newest_backup_age_hours,
    static_manifest_present: bool,
    pg_dump_available: bool,
    rate_limit_cache: str,
) -> list[Check]:
    """Turn the current environment into a list of pass/warn/fail rows.

    ``newest_backup_age_hours`` is ``None`` when no backup exists at all.
    ``db_engine`` is Django's ENGINE string (e.g. ``django.db.backends.postgresql``).
    ``media_backend`` is ``settings.MEDIA_BACKEND`` (``'s3'`` or ``'filesystem'``).
    """
    checks: list[Check] = []
    engine = (db_engine or '').lower()

    # 1. Debug must be off. This is the difference between a stack trace in a
    #    parent's browser and a plain 500 page.
    checks.append(Check(
        'debug',
        'DEBUG বন্ধ',
        OK if not debug else FAIL,
        'DEBUG=False' if not debug else
        'DEBUG=True চলছে — প্রতিটি এরর ব্যবহারকারীকে সোর্স পথ ও সেটিংস দেখাবে। '
        'হোস্টিংয়ের এনভায়রনমেন্টে DEBUG=False দিন।',
    ))

    # 2. A real SECRET_KEY. The fallback in settings.py is public in git.
    checks.append(Check(
        'secret_key',
        'SECRET_KEY বদলানো',
        FAIL if _is_insecure_secret(secret_key) else OK,
        'নিজস্ব SECRET_KEY সেট আছে' if not _is_insecure_secret(secret_key) else
        'ডিফল্ট/ছোট SECRET_KEY — সেশন ও CSRF টোকেন জাল করা সম্ভব। '
        'SECRET_KEY এনভায়রনমেন্ট ভ্যারিয়েবলে ৫০+ অক্ষরের নতুন কী দিন।',
    ))

    # 3. Explicit hosts. '*' plus a leaked hostname is an open redirect and a
    #    cache-poisoning vector (see students.E016).
    hosts = [h for h in (allowed_hosts or []) if h]
    if not hosts or '*' in hosts:
        checks.append(Check(
            'allowed_hosts', 'ALLOWED_HOSTS নির্দিষ্ট', FAIL,
            'ALLOWED_HOSTS খালি বা "*" — নির্দিষ্ট ডোমেইন দিন (যেমন '
            'school.example.com)।',
        ))
    else:
        checks.append(Check(
            'allowed_hosts', 'ALLOWED_HOSTS নির্দিষ্ট', OK,
            ', '.join(hosts[:3]) + (' …' if len(hosts) > 3 else ''),
        ))

    # 4. CSRF origins: without this the login POST fails with 403 behind a proxy.
    origins = [o for o in (csrf_trusted_origins or []) if o]
    checks.append(Check(
        'csrf_origins', 'CSRF_TRUSTED_ORIGINS', OK if origins else WARN,
        ', '.join(origins[:2]) if origins else
        'খালি — HTTPS প্রক্সির পেছনে লগইন POST-এ 403 আসতে পারে '
        '(https:// আপনার-ডোমেইন)।',
    ))

    # 5. Database engine. SQLite is fine for one user on a laptop; it is not
    #    fine for 3,500 students and 240 staff writing at once.
    if 'postgres' in engine:
        checks.append(Check(
            'db_engine', 'ডেটাবেস PostgreSQL', OK, 'PostgreSQL-এ চলছে',
        ))
        # 6. pg_dump is how the Postgres backup is taken; without it the daily
        #    cron job fails and nobody notices until a restore is needed.
        checks.append(Check(
            'pg_dump', 'pg_dump ইনস্টল', OK if pg_dump_available else FAIL,
            'pg_dump পাওয়া গেছে' if pg_dump_available else
            'pg_dump নেই — Postgres ব্যাকআপ নেওয়া যাবে না। '
            'postgresql-client ইনস্টল করুন বা deploy/backup-cron.Dockerfile ব্যবহার করুন।',
        ))
    else:
        checks.append(Check(
            'db_engine', 'ডেটাবেস PostgreSQL', WARN,
            f'SQLite চলছে ({engine or "unknown"}) — ৩,৫০০ শিক্ষার্থী ও ২৪০ কর্মীর '
            'একসাথে লেখার জন্য নয় ("database is locked")। DATABASE_URL দিয়ে Postgres-এ যান।',
        ))
        checks.append(Check(
            'pg_dump', 'pg_dump ইনস্টল', OK,
            'SQLite ব্যাকআপে pg_dump লাগে না (sqlite online backup ব্যবহার হয়)',
        ))

    # 7. Media in object storage, otherwise photos vanish on redeploy.
    if media_backend == 's3':
        checks.append(Check(
            'media_backend', 'ছবি/ফাইল বাকেটে (S3/R2)', OK, 'USE_S3 চালু — বাকেটে যাচ্ছে',
        ))
    else:
        checks.append(Check(
            'media_backend', 'ছবি/ফাইল বাকেটে (S3/R2)', WARN,
            'ফাইল লোকাল ডিস্কে — ক্লাউডে রিডিপ্লয়/রিস্টার্টে শিক্ষার্থীর ছবি হারাবে। '
            'USE_S3=True ও বাকেটের কী দিন (docs/FREE_TIER_MEDIA_STORAGE.md)।',
        ))

    # 8. Backup freshness. "We have backups" is a claim; this is the check.
    if newest_backup_age_hours is None:
        checks.append(Check(
            'backup_age', 'সাম্প্রতিক ব্যাকআপ', FAIL,
            'কোনো ব্যাকআপ পাওয়া যায়নি — আগে একটা নিন: python manage.py backup_data',
        ))
    elif newest_backup_age_hours > BACKUP_STALE_HOURS:
        checks.append(Check(
            'backup_age', 'সাম্প্রতিক ব্যাকআপ', WARN,
            f'সর্বশেষ ব্যাকআপ {newest_backup_age_hours:.1f} ঘণ্টা আগে '
            f'(সীমা {BACKUP_STALE_HOURS} ঘণ্টা) — ক্রন কাজ করছে কি না দেখুন।',
        ))
    else:
        checks.append(Check(
            'backup_age', 'সাম্প্রতিক ব্যাকআপ', OK,
            f'সর্বশেষ ব্যাকআপ {newest_backup_age_hours:.1f} ঘণ্টা আগে',
        ))

    # 9. Static manifest. With DEBUG=False staticfiles uses
    #    CompressedManifestStaticFilesStorage, which 500s on every {% static %}
    #    tag until collectstatic has run.
    if debug:
        checks.append(Check(
            'static_manifest', 'স্ট্যাটিক ফাইল (manifest)', OK,
            'DEBUG=True — manifest দরকার নেই',
        ))
    elif static_manifest_present:
        checks.append(Check(
            'static_manifest', 'স্ট্যাটিক ফাইল (manifest)', OK, 'staticfiles.json আছে',
        ))
    else:
        checks.append(Check(
            'static_manifest', 'স্ট্যাটিক ফাইল (manifest)', FAIL,
            'staticfiles/staticfiles.json নেই — DEBUG=False-এ প্রতিটি পেজ 500 দেবে। '
            'python manage.py collectstatic --noinput চালান (build command-এ রাখুন)।',
        ))

    # 10. Rate-limit counters. locmem counters are per worker: with gunicorn
    #     workers=2 the effective allowance silently doubles.
    if rate_limit_cache == 'db':
        checks.append(Check(
            'rate_limit_cache', 'রেট-লিমিট কাউন্টার শেয়ারড', OK, "RATE_LIMIT_CACHE=db",
        ))
    else:
        checks.append(Check(
            'rate_limit_cache', 'রেট-লিমিট কাউন্টার শেয়ারড', WARN,
            'RATE_LIMIT_CACHE=locmem — প্রতিটি worker আলাদা গুনে, তাই লগইন '
            'লকআউটের সীমা worker-সংখ্যার গুণ হয়ে যায়। RATE_LIMIT_CACHE=db দিন।',
        ))

    return checks


# ---------------------------------------------------------------------------
# Gathering the real values (only used by the management command)
# ---------------------------------------------------------------------------

def newest_backup_age_hours(backup_root: Path | None = None):
    """Age of the newest backup folder in hours, or ``None`` if there is none."""
    import datetime

    from students import backup_utils

    try:
        root = Path(backup_root) if backup_root else backup_utils.backup_root()
    except Exception:  # noqa: BLE001 - a broken setting must not crash the check
        return None
    if not root.is_dir():
        return None
    newest = None
    for child in root.iterdir():
        if not child.is_dir():
            continue
        try:
            mtime = child.stat().st_mtime
        except OSError:
            continue
        if newest is None or mtime > newest:
            newest = mtime
    if newest is None:
        return None
    now = datetime.datetime.now().timestamp()
    return max(0.0, (now - newest) / 3600.0)


def collect_environment() -> dict:
    """Read the live Django settings into the keywords `evaluate_checks` needs."""
    return {
        'debug': bool(settings.DEBUG),
        'secret_key': settings.SECRET_KEY or '',
        'allowed_hosts': list(getattr(settings, 'ALLOWED_HOSTS', []) or []),
        'csrf_trusted_origins': list(
            getattr(settings, 'CSRF_TRUSTED_ORIGINS', []) or []
        ),
        'db_engine': settings.DATABASES['default'].get('ENGINE', ''),
        'media_backend': getattr(settings, 'MEDIA_BACKEND', 'filesystem'),
        'newest_backup_age_hours': newest_backup_age_hours(),
        'static_manifest_present': (Path(settings.BASE_DIR) / 'staticfiles' / 'staticfiles.json').is_file(),
        'pg_dump_available': shutil.which('pg_dump') is not None,
        'rate_limit_cache': getattr(settings, 'RATE_LIMIT_CACHE', 'locmem'),
    }
