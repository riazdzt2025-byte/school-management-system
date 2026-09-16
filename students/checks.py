"""Deployment-time checks for upload storage (D-7, free-tier media).

Render's free tier restarts the container on every deploy and the filesystem it
starts with is empty. Media written to ``BASE_DIR/media`` therefore disappears,
and the app keeps working well enough that nobody notices until a parent
reports a missing photo. These checks surface that while it is still a line in
a build log instead of lost data.
"""
import importlib.util
from pathlib import Path

from django.conf import settings
from django.core.checks import Error, Tags, Warning, register


def _module_available(name):
    return importlib.util.find_spec(name) is not None


@register(Tags.compatibility)
def check_s3_dependencies(app_configs=None, **kwargs):
    """USE_S3 without django-storages/boto3 is a broken deployment, not a
    warning to read later — the first upload attempt would 500.

    Runs on every ``manage.py check`` (a build command, a CI step) and stays
    silent in development, where USE_S3 is simply not set.
    """
    if not getattr(settings, 'MEDIA_IS_REMOTE', False):
        return []
    return [
        Error(
            f"USE_S3 is set but the '{missing}' package is not installed.",
            hint="requirements.txt lists it, so this is a build problem: check the "
                 "Render build log for a failed/partial `pip install -r requirements.txt`.",
            id='students.E011',
        )
        for missing in ('storages', 'boto3')
        if not _module_available(missing)
    ]


@register(Tags.compatibility, deploy=True)
def check_media_storage_durable(app_configs=None, **kwargs):
    """Warn when media is heading for storage that a redeploy wipes.

    ``deploy=True`` keeps this out of every plain ``check``/test run: a local
    ``BASE_DIR/media`` is exactly what development wants. Production is asked
    to run ``manage.py check --deploy`` (see DEPLOY_NOTES.md / the runbook).
    """
    if getattr(settings, 'MEDIA_IS_REMOTE', False):
        # A bucket is off-box by construction — nothing on this disk to lose.
        return []
    # DEBUG=False is the signal for "this is a deployment, not a laptop".
    if getattr(settings, 'DEBUG', True):
        return []
    media_root = Path(str(getattr(settings, 'MEDIA_ROOT', '')))
    try:
        inside_app_tree = media_root.resolve().is_relative_to(Path(settings.BASE_DIR).resolve())
    except OSError:
        # An unusable MEDIA_ROOT is a different problem; do not guess here.
        inside_app_tree = False
    if not inside_app_tree:
        return []
    return [
        Warning(
            "Uploaded files are written inside the app directory, which is "
            "wiped on every deploy — student photos will be lost.",
            hint="Set USE_S3=True with AWS_STORAGE_BUCKET_NAME / AWS_ACCESS_KEY_ID / "
                 "AWS_SECRET_ACCESS_KEY to store media in S3-compatible object "
                 "storage, or point MEDIA_ROOT at a persistent disk. "
                 "See docs/FREE_TIER_MEDIA_STORAGE.md.",
            id='students.W010',
        )
    ]


@register(Tags.compatibility)
def check_single_writable_database(app_configs=None, **kwargs):
    """One writable database — the rule that keeps "which one is true?" answerable.

    Redundancy in this system comes from read-only backups
    (`manage.py backup_data`), never from a second live database: two writable
    copies of the student table diverge within a day, and no procedure here can
    merge them. This turns the rule in docs/DATA_SAFETY_STATUS.md §2 from
    something a reviewer greps for into something `manage.py check` reports.

    A second alias is a Warning rather than an Error because Django itself
    supports read replicas with a router; if one is ever added deliberately,
    silence it with `SILENCED_SYSTEM_CHECKS` and write down which database the
    backups come from.

    The id is W015 rather than W012 on purpose: `docs/PROJECT_STATUS.md` lists
    Django's own `security.W012` among the expected `check --deploy` warnings,
    and two different "W012"s in one document is how a real warning gets
    skimmed past.
    """
    aliases = sorted(getattr(settings, 'DATABASES', {}) or {})
    if len(aliases) <= 1:
        return []
    return [
        Warning(
            f"{len(aliases)} databases are configured ({', '.join(aliases)}). "
            "This system is designed around exactly ONE writable database plus "
            "read-only backups.",
            hint="Remove the extra alias, or — if it is a deliberate read "
                 "replica — document which one backup_data snapshots and add "
                 "its id to SILENCED_SYSTEM_CHECKS. Never keep two writable "
                 "copies of the student data. See docs/DATA_SAFETY_STATUS.md §2.",
            id='students.W015',
        )
    ]


def _backup_root_path():
    """The resolved backup root, or None when it cannot be determined."""
    from students import backup_utils as bak
    try:
        return Path(str(bak.backup_root())).resolve()
    except (OSError, RuntimeError):
        return None


@register(Tags.security, deploy=True)
def check_backup_root_not_web_served(app_configs=None, **kwargs):
    """Backups must not sit where a web server will serve them.

    A `backups/` folder under MEDIA_ROOT is downloadable by anyone who can
    guess `/media/backups/backup-<stamp>/db.sqlite3` — and the timestamp is in
    the log. Under STATIC_ROOT it is worse: `collectstatic` copies it into the
    served tree on every deploy. Both are a full-PII exposure, so they are
    Errors, not warnings.
    """
    root = _backup_root_path()
    if root is None:
        return []
    served = []
    for label, attr in (('MEDIA_ROOT', 'MEDIA_ROOT'), ('STATIC_ROOT', 'STATIC_ROOT')):
        value = getattr(settings, attr, None)
        if not value:
            continue
        try:
            served_root = Path(str(value)).resolve()
        except OSError:
            continue
        if root == served_root or root.is_relative_to(served_root):
            served.append(label)
    if not served:
        return []
    return [
        Error(
            f"The backup directory ({root}) is inside {' and '.join(served)}, "
            "which is served over HTTP — a backup is a complete copy of the "
            "school's PII.",
            hint="Point P0B_BACKUP_ROOT (or --backup-root) at a directory "
                 "outside every served tree, e.g. /data/backups on a persistent "
                 "disk. See docs/BACKUP_RESTORE_GUIDE.md §4.",
            id='students.E013',
        )
    ]


@register(Tags.security, deploy=True)
def check_backup_root_durable(app_configs=None, **kwargs):
    """Warn when backups are written inside the app directory on a deployment.

    Same failure as ephemeral media (W010), one step later in the incident: on a
    container platform without a persistent disk the backup is written, reported
    healthy, and wiped with the container on the next deploy — so the night the
    database is lost, the backup is gone too. Development keeps the convenient
    `./backups` default (DEBUG=True short-circuits).
    """
    if getattr(settings, 'DEBUG', True):
        return []
    root = _backup_root_path()
    if root is None:
        return []
    try:
        base = Path(settings.BASE_DIR).resolve()
    except OSError:
        return []
    if not (root == base or root.is_relative_to(base)):
        return []
    return [
        Warning(
            f"Backups are written inside the app directory ({root}), which a "
            "container platform wipes on every deploy/restart.",
            hint="Set P0B_BACKUP_ROOT to a persistent disk, and/or configure "
                 "BACKUP_OBJECT_STORAGE_* so every backup also lands in a "
                 "bucket off this machine. See docs/BACKUP_RESTORE_GUIDE.md §4.3.",
            id='students.W014',
        )
    ]
