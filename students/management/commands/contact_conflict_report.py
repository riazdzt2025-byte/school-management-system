"""Read-only report of legacy vs guardian contact data, for the unification
of the contact number into the single "Guardian Contact Number /
অভিভাবকের যোগাযোগ নম্বর" column.

On a database that still has the legacy columns (migrations up to 0039) it
lists rows where the two columns disagree and how many blank guardian
numbers the safe backfill would fill. After migration 0040 removed the
legacy columns, it says so and points at the AuditLog entries that archived
the dropped values. It never writes anything.

Usage:
    python manage.py contact_conflict_report
    python manage.py contact_conflict_report --limit 20
"""
from django.core.exceptions import FieldDoesNotExist
from django.core.management.base import BaseCommand
from django.db.models import Q

from students.models import AdmissionApplication, Student


class Command(BaseCommand):
    help = (
        'Dry-run report: where the legacy contact column and the guardian '
        'contact column disagree, and how many blank guardian numbers the '
        'safe backfill migration would fill. Changes nothing.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit', type=int, default=50,
            help='Maximum number of conflicting rows to list per model (default 50).',
        )

    def _legacy_columns_present(self):
        """The legacy columns were dropped in migration 0040; against a
        database that has already applied it there is nothing to compare."""
        for model, field in ((Student, 'contact_no'),
                             (AdmissionApplication, 'applicant_contact_no')):
            try:
                model._meta.get_field(field)
            except FieldDoesNotExist:
                return False
        return True

    def _guardian_empty(self):
        return Q(guardian_contact_no='') | Q(guardian_contact_no__isnull=True)

    def _report_model(self, label, queryset, legacy_field, describe, limit):
        guardian = 'guardian_contact_no'
        # Both columns set (blank values don't count as set).
        legacy_set = ~Q(**{f'{legacy_field}': ''}) & ~Q(**{f'{legacy_field}__isnull': True})
        guardian_set = ~Q(**{guardian: ''}) & ~Q(**{guardian + '__isnull': True})
        conflicts = list(queryset.filter(legacy_set & guardian_set).iterator())

        out = [f'== {label} ==']
        if conflicts:
            different = [
                row for row in conflicts
                if (getattr(row, legacy_field) or '').strip()
                != (getattr(row, guardian) or '').strip()
            ]
            out.append(
                f'CONFLICT: {len(different)} row(s) have BOTH a legacy '
                f'{legacy_field} and a different guardian_contact_no. The '
                'migration does NOT touch these — decide manually which '
                'number is correct.'
            )
            for row in different[:limit]:
                out.append(
                    f'  {describe(row)} | legacy {legacy_field}='
                    f'{getattr(row, legacy_field)!r} | guardian='
                    f'{getattr(row, guardian)!r}'
                )
            if len(different) > limit:
                out.append(f'  … and {len(different) - limit} more (raise --limit to see all)')
            same = len(conflicts) - len(different)
            if same:
                out.append(
                    f'{same} row(s) have the same number in both columns — '
                    'no action needed; the legacy column can be dropped later.'
                )
        else:
            out.append('CONFLICT: none.')

        backfill_pending = queryset.filter(
            self._guardian_empty() & legacy_set
        ).count()
        out.append(
            f'BACKFILL: {backfill_pending} row(s) have a blank guardian '
            f'contact but a legacy {legacy_field} — migration 0039 copies '
            'the legacy number in (safe: guardian is blank).'
        )
        guardian_only = queryset.filter(guardian_set).count()
        out.append(
            f'OK: {guardian_only} row(s) already carry a guardian contact number.'
        )
        return out

    def handle(self, *args, **options):
        if not self._legacy_columns_present():
            self.stdout.write(
                'The legacy contact columns (Student.contact_no and '
                'AdmissionApplication.applicant_contact_no) were already '
                'removed by migration students.0040 — there is nothing to '
                'compare.\n'
                'Any legacy number that differed from its guardian contact '
                "number was archived first: look for AuditLog entries with "
                "action 'legacy_contact_dropped'."
            )
            return
        limit = options['limit']
        lines = self._report_model(
            'Students (Student.contact_no vs Student.guardian_contact_no)',
            Student.objects.all(), 'contact_no',
            lambda s: f'{s.student_id or "(no id)"} {s.name}', limit,
        )
        lines.append('')
        lines += self._report_model(
            'Admission applications (AdmissionApplication.applicant_contact_no '
            'vs AdmissionApplication.guardian_contact_no)',
            AdmissionApplication.objects.all(), 'applicant_contact_no',
            lambda a: f'{a.application_number} {a.applicant_name}', limit,
        )
        lines.append('')
        lines.append('This command is a dry run — nothing was changed.')
        self.stdout.write('\n'.join(lines))
