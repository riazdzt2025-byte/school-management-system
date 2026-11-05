"""Read-only report on the single "Guardian Contact Number /
অভিভাবকের যোগাযোগ নম্বর" column.

Current database (after migration 0040): lists guardian numbers shared by
more than one student / application (siblings — allowed by owner decision
OF-01, reported for information only), existing numbers that do not match
the 11-digit Bangladeshi mobile format enforced on new entries, and how many
legacy numbers were archived to AuditLog when the old columns were dropped.

Old database (before migration 0040) — the original purpose:

On a database that still has the legacy columns (migrations up to 0039) it
lists rows where the two columns disagree and how many blank guardian
numbers the safe backfill would fill. After migration 0040 removed the
legacy columns, it says so and points at the AuditLog entries that archived
the dropped values. It never writes anything.

Usage:
    python manage.py contact_conflict_report
    python manage.py contact_conflict_report --limit 20
"""
import re

from django.core.exceptions import FieldDoesNotExist
from django.core.management.base import BaseCommand
from django.db.models import Count, Q

from students.models import (
    GUARDIAN_CONTACT_RE, AdmissionApplication, AuditLog, Student,
)


class Command(BaseCommand):
    help = (
        'Dry-run report on guardian contacts: shared (sibling) numbers, '
        'non-standard existing numbers, archived legacy numbers; on a pre-0040 '
        'database also where the legacy contact column and the guardian '
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

    def _current_report(self, limit):
        """Report for the single-column schema (after migration 0040)."""
        out = []
        for label, qs, describe in (
            ('Students', Student.objects.all(),
             lambda r: f'{r.student_id or "(no id)"} {r.name}'),
            ('Admission applications', AdmissionApplication.objects.all(),
             lambda r: f'{r.application_number} {r.applicant_name}'),
        ):
            filled = qs.exclude(guardian_contact_no='').exclude(
                guardian_contact_no__isnull=True)
            out.append(f'== {label} (guardian_contact_no) ==')
            out.append(f'Total with a guardian number: {filled.count()}')

            shared = list(
                filled.values('guardian_contact_no')
                .annotate(n=Count('pk')).filter(n__gt=1)
                .order_by('-n', 'guardian_contact_no')
            )
            out.append(
                f'SHARED: {len(shared)} number(s) used by more than one row '
                '(siblings are allowed — information only, nothing blocked).'
            )
            for entry in shared[:limit]:
                number = entry['guardian_contact_no']
                rows = ', '.join(
                    describe(r) for r in filled.filter(guardian_contact_no=number)[:10]
                )
                out.append(f'  {number} x{entry["n"]}: {rows}')
            if len(shared) > limit:
                out.append(f'  … and {len(shared) - limit} more (raise --limit to see all)')

            pattern = re.compile(GUARDIAN_CONTACT_RE)
            invalid = [
                r for r in filled.iterator()
                if not pattern.match(r.guardian_contact_no.strip())
            ]
            out.append(
                f'FORMAT: {len(invalid)} existing number(s) are not an '
                '11-digit Bangladeshi mobile (01[3-9]XXXXXXXX). They were '
                'not changed; they must be corrected the next time the '
                'record is edited.'
            )
            for r in invalid[:limit]:
                out.append(f'  {describe(r)} | {r.guardian_contact_no!r}')
            if len(invalid) > limit:
                out.append(f'  … and {len(invalid) - limit} more (raise --limit to see all)')
            out.append('')

        archived = AuditLog.objects.filter(action='legacy_contact_dropped')
        total = sum(
            len((entry.details or {}).get('dropped_rows', []))
            for entry in archived
        )
        out.append(
            f'ARCHIVE: {archived.count()} AuditLog entr(y/ies) with action '
            f"'legacy_contact_dropped' hold {total} legacy number(s) "
            "(details.dropped_rows[].legacy_contact) that differed from the "
            'guardian number when the old columns were dropped.'
        )
        return out

    def handle(self, *args, **options):
        limit = options['limit']
        if not self._legacy_columns_present():
            self.stdout.write(
                'The legacy contact columns (Student.contact_no and '
                'AdmissionApplication.applicant_contact_no) were already '
                'removed by migration students.0040 — there is nothing to '
                'compare.\n'
                'Any legacy number that differed from its guardian contact '
                "number was archived first: look for AuditLog entries with "
                "action 'legacy_contact_dropped'.\n"
            )
            self.stdout.write('\n'.join(self._current_report(limit)))
            self.stdout.write('\nThis command is a dry run — nothing was changed.')
            return
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
