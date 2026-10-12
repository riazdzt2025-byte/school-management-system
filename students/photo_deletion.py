"""Durable outbox and retry worker for student-photo storage deletion."""
from __future__ import annotations

import logging
from datetime import timedelta

from django.core.files.storage import storages
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

DEFAULT_PHOTO_STORAGE_ALIAS = 'default'
INITIAL_RETRY_DELAY_SECONDS = 60
MAX_RETRY_DELAY_SECONDS = 24 * 60 * 60


def enqueue_student_photo_deletion(name, *, using='default', storage_alias=DEFAULT_PHOTO_STORAGE_ALIAS):
    """Persist a delete intent with the photo change and try it after commit."""
    if not name:
        return None

    # Import lazily because models.py imports photo_uploads for the ImageField
    # validator, while signals call this helper after the app registry is ready.
    from .models import StudentPhotoDeletionJob

    job = StudentPhotoDeletionJob.objects.using(using).create(
        storage_alias=storage_alias,
        name=name,
    )
    # Preserve immediate cleanup when storage is healthy. Since the outbox row
    # is committed first, a process crash or backend error cannot lose intent.
    transaction.on_commit(
        lambda job_id=job.pk: process_student_photo_deletion_job(
            job_id,
            using=using,
        ),
        using=using,
        robust=True,
    )
    return job


def _retry_delay_seconds(attempts):
    """Exponential retry delay capped at one day; first retry is after 60s."""
    exponent = min(max(attempts - 1, 0), 20)
    return min(INITIAL_RETRY_DELAY_SECONDS * (2 ** exponent), MAX_RETRY_DELAY_SECONDS)


def process_student_photo_deletion_job(job_id, *, using='default', now=None):
    """Attempt one due job, deleting it only after storage confirms success."""
    from .models import StudentPhotoDeletionJob

    attempted_at = now or timezone.now()
    manager = StudentPhotoDeletionJob.objects.using(using)
    with transaction.atomic(using=using):
        job = manager.select_for_update().filter(pk=job_id).first()
        if job is None or job.next_attempt_at > attempted_at:
            return 'skipped'

        try:
            storages[job.storage_alias].delete(job.name)
        except Exception as exc:  # storage backends fail independently of the DB
            attempts = job.attempts + 1
            delay_seconds = _retry_delay_seconds(attempts)
            manager.filter(pk=job.pk).update(
                attempts=attempts,
                last_attempt_at=attempted_at,
                next_attempt_at=attempted_at + timedelta(seconds=delay_seconds),
                last_error_type=type(exc).__name__[:120],
            )
            logger.error(
                'Student photo deletion failed; retry scheduled '
                '(job_id=%s backend=%s error_type=%s retry_seconds=%s).',
                job.pk,
                job.storage_alias,
                type(exc).__name__,
                delay_seconds,
            )
            return 'retrying'

        # Filtered delete avoids recreating a row if a concurrent worker already
        # completed this idempotent job between selecting and deleting it.
        manager.filter(pk=job.pk).delete()
        return 'deleted'


def process_due_student_photo_deletions(*, limit=100, using='default', now=None):
    """Process a bounded set of due objects, retaining failures for retry.

    The scheduler should run one command instance at a time on SQLite. On
    databases with row-lock support, concurrent workers serialize each job.
    """
    if limit < 1:
        raise ValueError('limit must be a positive integer')

    from .models import StudentPhotoDeletionJob

    attempted_at = now or timezone.now()
    job_ids = list(
        StudentPhotoDeletionJob.objects.using(using)
        .filter(next_attempt_at__lte=attempted_at)
        .order_by('next_attempt_at', 'pk')
        .values_list('pk', flat=True)[:limit]
    )

    deleted = retrying = 0
    for job_id in job_ids:
        result = process_student_photo_deletion_job(
            job_id,
            using=using,
            now=attempted_at,
        )
        if result == 'deleted':
            deleted += 1
        elif result == 'retrying':
            retrying += 1

    return {'processed': deleted + retrying, 'deleted': deleted, 'retrying': retrying}
