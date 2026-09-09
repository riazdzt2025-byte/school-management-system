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
