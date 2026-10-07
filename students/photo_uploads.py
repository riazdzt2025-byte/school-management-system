"""Validation, opaque names, and post-commit cleanup for student photos."""
from __future__ import annotations

import logging
import os
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import transaction

logger = logging.getLogger(__name__)

PHOTO_MAX_BYTES = 2 * 1024 * 1024
PHOTO_MIN_DIMENSION = 300
PHOTO_MAX_DIMENSION = 4096
PHOTO_ALLOWED_EXTENSIONS = frozenset({'.jpg', '.jpeg', '.png', '.gif'})


def validate_student_photo(upload):
    """Accept only small, decodable raster photos within the agreed dimensions.

    Django's ImageField has already decoded and verified an uploaded file when
    this validator is called from a ModelForm. The fallback Pillow path keeps
    ``full_clean()`` callers honest too.
    """
    if not upload:
        return

    # Keep legacy stored files usable when an unrelated student field is edited;
    # policy checks apply to new uploads, not existing committed FieldFile values.
    if getattr(upload, '_committed', False):
        return

    if upload.size > PHOTO_MAX_BYTES:
        raise ValidationError('Photo must be 2 MiB or smaller.')

    extension = os.path.splitext(getattr(upload, 'name', ''))[1].lower()
    if extension not in PHOTO_ALLOWED_EXTENSIONS:
        raise ValidationError('Only JPG, PNG or GIF images are allowed.')

    content_type = getattr(upload, 'content_type', '') or ''
    if content_type and not content_type.lower().startswith('image/'):
        raise ValidationError('Uploaded file is not a valid image.')

    image = getattr(upload, 'image', None)
    if image is not None:
        width, height = image.size
    else:
        # Normally the ImageField supplies ``upload.image``. This fallback is
        # useful for explicit model validation and never trusts the MIME header.
        from PIL import Image, UnidentifiedImageError

        try:
            position = upload.tell()
        except (AttributeError, OSError, ValueError):
            position = None
        try:
            with Image.open(upload) as opened:
                width, height = opened.size
                opened.verify()
        except (
            Image.DecompressionBombError, OSError, SyntaxError,
            UnidentifiedImageError, ValueError,
        ) as exc:
            raise ValidationError('Uploaded file is not a valid image.') from exc
        finally:
            if position is not None and hasattr(upload, 'seek'):
                try:
                    upload.seek(position)
                except (OSError, ValueError):
                    pass

    if width < PHOTO_MIN_DIMENSION or height < PHOTO_MIN_DIMENSION:
        raise ValidationError(
            f'Photo must be at least {PHOTO_MIN_DIMENSION}×{PHOTO_MIN_DIMENSION} pixels.'
        )
    if width > PHOTO_MAX_DIMENSION or height > PHOTO_MAX_DIMENSION:
        raise ValidationError(
            f'Photo dimensions cannot exceed {PHOTO_MAX_DIMENSION}×{PHOTO_MAX_DIMENSION} pixels.'
        )


def student_photo_upload_to(instance, filename):
    """Store new photos under opaque, path-safe names; never preserve PII names."""
    extension = os.path.splitext(str(filename).replace('\\', '/'))[1].lower()
    if extension not in PHOTO_ALLOWED_EXTENSIONS:
        extension = '.img'
    return f'student_photos/{uuid4().hex}{extension}'


def delete_photo_after_commit(storage, name):
    """Delete an old photo only once its database reference is committed.

    If a remote backend is temporarily unavailable, log a generic error without
    exposing a potentially identifying legacy filename or object key.
    """
    if not name:
        return

    def _delete():
        try:
            storage.delete(name)
        except Exception:  # storage backends can fail independently of the DB
            logger.error(
                'Unable to delete student photo from storage (backend=%s).',
                type(storage).__name__,
            )

    transaction.on_commit(_delete, robust=True)
