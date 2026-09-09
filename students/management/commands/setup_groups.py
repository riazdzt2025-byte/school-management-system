"""python manage.py setup_groups

Create/reconcile the department groups and their permissions from a *single*
source of truth: ``students/permissions.py`` (``ensure_default_groups``),
which is also wired into ``post_migrate``.

Historically this command carried its own permission map duplicate that drifted
from ``permissions.py`` (the Exam group had ``delete_exam`` here but not in
``permissions.py``). That was removed — run this command after a migrate and it
produces exactly the same permission sets ``ensure_default_groups`` does.
"""
from django.core.management.base import BaseCommand

from students.permissions import ensure_default_groups


class Command(BaseCommand):
    help = "Create/update department groups from the single source of truth (permissions.py)."

    def handle(self, *args, **options):
        group_names = ensure_default_groups()
        self.stdout.write(self.style.SUCCESS(
            "Department groups reconciled from students/permissions.py: "
            + ", ".join(sorted(group_names))
        ))
