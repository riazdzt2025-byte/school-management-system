from django.apps import AppConfig


class StudentsConfig(AppConfig):
    name = 'students'

    def ready(self):
        from .permissions import ensure_default_groups
        ensure_default_groups()
