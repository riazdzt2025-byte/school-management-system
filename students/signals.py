"""Keep student photo files in sync with their database references."""
from django.db.models.signals import post_delete, post_save, pre_save

from .models import Student
from .photo_uploads import delete_photo_after_commit


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


def _delete_replaced_photo(sender, instance, created=False, raw=False, **kwargs):
    if raw or not hasattr(instance, '_previous_photo_name'):
        return

    old_name = instance._previous_photo_name
    new_name = instance.photo.name if instance.photo else ''
    if old_name and old_name != new_name:
        delete_photo_after_commit(sender._meta.get_field('photo').storage, old_name)

    del instance._previous_photo_name


def _delete_hard_deleted_photo(sender, instance, **kwargs):
    if instance.photo and instance.photo.name:
        delete_photo_after_commit(instance.photo.storage, instance.photo.name)


pre_save.connect(
    _remember_previous_photo,
    sender=Student,
    dispatch_uid='students.remember_previous_photo',
)
post_save.connect(
    _delete_replaced_photo,
    sender=Student,
    dispatch_uid='students.delete_replaced_photo',
)
post_delete.connect(
    _delete_hard_deleted_photo,
    sender=Student,
    dispatch_uid='students.delete_hard_deleted_photo',
)
