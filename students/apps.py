from django.apps import AppConfig
from django.db.models.signals import post_migrate


def _sync_default_groups(sender, **kwargs):
    from .permissions import ensure_default_groups
    ensure_default_groups()


class StudentsConfig(AppConfig):
    name = 'students'

    def ready(self):
        # Run after migrations instead of at import time: querying the database
        # from ready() crashes on a fresh/unmigrated database (e.g. the very
        # first `manage.py migrate`).
        post_migrate.connect(_sync_default_groups, sender=self)
