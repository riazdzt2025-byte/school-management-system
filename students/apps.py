from django.apps import AppConfig
from django.db.models.signals import post_migrate


def _sync_default_groups(sender, **kwargs):
    from .permissions import ensure_default_groups
    ensure_default_groups()


class StudentsConfig(AppConfig):
    name = 'students'
    # The migrations already create BigAutoField primary keys (they were generated
    # with this default), but the project settings never declared one, so every
    # model in this app raised models.W042. Declaring it keeps the models and the
    # schema in sync — no new migration and no table rebuild.
    default_auto_field = 'django.db.models.BigAutoField'

    def ready(self):
        # Registers the deployment checks in students/checks.py (media storage
        # durability). Imported here rather than at module scope so it runs once,
        # after the app registry is populated.
        from . import checks  # noqa: F401

        # Run after migrations instead of at import time: querying the database
        # from ready() crashes on a fresh/unmigrated database (e.g. the very
        # first `manage.py migrate`).
        post_migrate.connect(_sync_default_groups, sender=self)
