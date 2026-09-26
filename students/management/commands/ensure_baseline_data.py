"""Ensure the baseline data a freshly migrated (or reset) database needs.

Render's free tier has no Shell access, so `migrate` + `loaddata` +
`createsuperuser` cannot be typed interactively on the server. This command
lets the Start Command (`scripts/render_start.sh`) self-heal a blank database:

1. loads `students/fixtures/institutions.json` — **only when the institution
   table is empty**, so institutions edited or deleted in the admin are never
   overwritten on restart;
2. creates the superuser named by ``DJANGO_SUPERUSER_USERNAME`` (password from
   ``DJANGO_SUPERUSER_PASSWORD``) when that user does not exist yet.

The command is idempotent and never raises: on an already-initialised
database it just reports what already exists and exits 0, so it is safe to
run on every boot. If the tables do not exist yet it says so and points at
`manage.py migrate` instead of crashing (a broken database should fail in
`migrate`, not here).

Environment variables (set them in the Render dashboard, Environment):

    DJANGO_SUPERUSER_USERNAME   admin username to create when missing
    DJANGO_SUPERUSER_PASSWORD   that user's password
    DJANGO_SUPERUSER_EMAIL      optional, defaults to <username>@example.com
"""
import os

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import OperationalError, ProgrammingError

from students.models import Institution

INSTITUTIONS_FIXTURE = 'students/fixtures/institutions.json'


class Command(BaseCommand):
    help = (
        'Load the institutions fixture (only when the table is empty) and '
        'create the superuser from DJANGO_SUPERUSER_* env vars (only when '
        'that user does not exist). Safe to run on every boot.'
    )

    def handle(self, *args, **options):
        self._ensure_institutions()
        self._ensure_superuser()

    # ------------------------------------------------------------------ #

    def _ensure_institutions(self):
        try:
            count = Institution.objects.count()
        except (OperationalError, ProgrammingError) as exc:
            self.stdout.write(self.style.WARNING(
                'Could not read the students_institution table (%s). '
                'Run `python manage.py migrate` first.' % exc.__class__.__name__))
            return

        if count:
            self.stdout.write(
                'Institutions: %d already present — fixture not reloaded '
                '(so admin edits are kept).' % count)
            return

        try:
            call_command('loaddata', INSTITUTIONS_FIXTURE, verbosity=0)
        except Exception as exc:  # noqa: BLE001 — never block startup
            self.stdout.write(self.style.WARNING(
                'Could not load %s: %s' % (INSTITUTIONS_FIXTURE, exc)))
            return

        self.stdout.write(self.style.SUCCESS(
            'Institutions: fixture loaded into the empty table '
            '(%d rows).' % Institution.objects.count()))

    def _ensure_superuser(self):
        User = get_user_model()
        username = os.environ.get('DJANGO_SUPERUSER_USERNAME', '').strip()
        password = os.environ.get('DJANGO_SUPERUSER_PASSWORD', '')
        email = os.environ.get('DJANGO_SUPERUSER_EMAIL', '').strip()

        try:
            if username and not password:
                self.stdout.write(self.style.WARNING(
                    'DJANGO_SUPERUSER_USERNAME is set but DJANGO_SUPERUSER_PASSWORD '
                    'is empty — superuser not created.'))
                return

            if username and password:
                lookup = {User.USERNAME_FIELD: username}
                if User.objects.filter(**lookup).exists():
                    self.stdout.write(
                        'Superuser: %r already exists — nothing to do.' % username)
                    return
                User.objects.create_superuser(
                    username=username,
                    email=email or '%s@example.com' % username,
                    password=password,
                )
                self.stdout.write(self.style.SUCCESS(
                    'Superuser: %r created from DJANGO_SUPERUSER_* environment '
                    'variables.' % username))
                return

            # No env vars configured: only report when the database has no admin
            # at all, so an operator immediately knows why they cannot log in.
            if not User.objects.filter(is_superuser=True).exists():
                self.stdout.write(self.style.WARNING(
                    'No superuser exists and DJANGO_SUPERUSER_USERNAME / '
                    'DJANGO_SUPERUSER_PASSWORD are not set. Set them as '
                    'environment variables and restart, or run '
                    '`python manage.py createsuperuser` from a machine that can '
                    'reach this database (see docs/RENDER_500_LOGIN_FIX.md).'))
            else:
                self.stdout.write(
                    'Superuser: at least one already exists — nothing to do.')
        except (OperationalError, ProgrammingError) as exc:
            self.stdout.write(self.style.WARNING(
                'Could not read the %s table (%s). '
                'Run `python manage.py migrate` first.'
                % (User._meta.db_table, exc.__class__.__name__)))
