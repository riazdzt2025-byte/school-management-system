"""Tests for ``manage.py reset_sequences``.

The interesting case (PostgreSQL) needs a live Postgres server, which CI has and
this suite does not; it is exercised by the deploy runbook's verification step.
What must hold everywhere is that the command is *safe*: on SQLite it must be a
no-op that says so, instead of pretending to have fixed something.
"""
import io

from django.core.management import call_command
from django.test import TestCase


class ResetSequencesTests(TestCase):
    def test_sqlite_is_a_clear_no_op(self):
        out = io.StringIO()
        call_command('reset_sequences', stdout=out)
        text = out.getvalue()
        self.assertIn('sqlite', text)
        self.assertIn('দরকার নেই', text)

    def test_dry_run_is_also_safe_on_sqlite(self):
        out = io.StringIO()
        call_command('reset_sequences', '--dry-run', stdout=out)
        self.assertIn('দরকার নেই', out.getvalue())

    def test_app_filter_is_accepted(self):
        out = io.StringIO()
        call_command('reset_sequences', '--app', 'students', stdout=out)
        self.assertIn('sqlite', out.getvalue())
