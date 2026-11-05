"""Queue student-photo cleanup atomically with database reference changes."""
from django.conf import settings
from django.db.models.signals import post_delete, post_save, pre_save

from .models import Student
from .photo_deletion import enqueue_student_photo_deletion


def _remember_previous_photo(sender, instance, raw=False, using='default', update_fields=None, **kwargs):
    if raw or instance._state.adding:
        return
    if update_fields is not None and 'photo' not in update_fields:
        return
    current_photo = instance.photo
    if getattr(current_photo, '_committed', False) and current_photo:
        return

    instance._previous_photo_name = sender._base_manager.using(using).filter(
        pk=instance.pk,
    ).values_list('photo', flat=True).first()


def _queue_replaced_photo(sender, instance, created=False, raw=False, using='default', **kwargs):
    if raw or not hasattr(instance, '_previous_photo_name'):
        return

    old_name = instance._previous_photo_name
    new_name = instance.photo.name if instance.photo else ''
    if old_name and old_name != new_name:
        enqueue_student_photo_deletion(old_name, using=using)

    del instance._previous_photo_name


def _queue_hard_deleted_photo(sender, instance, using='default', **kwargs):
    """Queue the storage delete for a hard-deleted row.

    ``DELETE_MEDIA_ON_PURGE=False`` is an owner-controlled retention choice for
    audit/legal reasons, so a purge must not quietly delete the file. Photo
    replace/clear keep queueing a delete: there the database reference is gone
    by explicit user action and keeping the bytes would leak an orphan.
    """
    if not getattr(settings, 'DELETE_MEDIA_ON_PURGE', True):
        return
    if instance.photo and instance.photo.name:
        enqueue_student_photo_deletion(instance.photo.name, using=using)


pre_save.connect(
    _remember_previous_photo,
    sender=Student,
    dispatch_uid='students.remember_previous_photo',
)
post_save.connect(
    _queue_replaced_photo,
    sender=Student,
    dispatch_uid='students.queue_replaced_photo',
)
post_delete.connect(
    _queue_hard_deleted_photo,
    sender=Student,
    dispatch_uid='students.queue_hard_deleted_photo',
)
