"""Find and merge Subject rows that are really the same subject.

Subjects accumulated duplicates over time because the seeded curriculum list
and hand-added rows use different spellings and codes, e.g.

    Bangla 1st Paper / BANGLA FIRST PAPER
    Bangla 2nd Paper / Bangla Second Paper

Duplicates make the marks-entry dropdown confusing and split a student's marks
across two subject rows. This command groups subjects by a normalised name,
keeps one row per group, repoints every reference at it, and deletes the rest.

It is a DRY RUN by default: run it, read the report, then re-run with --apply.
"""

import re
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count

from students.models import (
    ExamMark,
    StudentSubject,
    Subject,
    SubjectMarkSetting,
    SubjectRequirement,
)

# Spelling variants that should collapse onto the same canonical word.
_WORD_ALIASES = {
    'first': '1st',
    'second': '2nd',
    'third': '3rd',
    'fourth': '4th',
    'paper1': '1st paper',
    'and': '&',
}


def normalise_name(name):
    """Reduce a subject name to a comparable key.

    'BANGLA FIRST PAPER' and 'Bangla 1st Paper' both become 'bangla 1st paper'.
    """
    text = (name or '').strip().lower()
    text = text.replace('&', ' & ')
    text = re.sub(r'[^a-z0-9&]+', ' ', text)
    words = [_WORD_ALIASES.get(word, word) for word in text.split()]
    text = ' '.join(words)
    return re.sub(r'\s+', ' ', text).strip()


class Command(BaseCommand):
    help = 'Merge duplicate Subject rows (dry run unless --apply is passed).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply', action='store_true',
            help='Actually merge. Without this flag the command only reports.',
        )

    def handle(self, *args, **options):
        apply_changes = options['apply']

        groups = defaultdict(list)
        for subject in Subject.objects.all().order_by('pk'):
            groups[normalise_name(subject.name)].append(subject)

        duplicate_groups = {k: v for k, v in groups.items() if len(v) > 1}

        if not duplicate_groups:
            self.stdout.write(self.style.SUCCESS('No duplicate subjects found.'))
            return

        # Reference counts decide which row to keep.
        usage = defaultdict(int)
        for model, field in (
            (ExamMark, 'subject'),
            (StudentSubject, 'subject'),
            (SubjectRequirement, 'subject'),
            (SubjectMarkSetting, 'subject'),
        ):
            for row in model.objects.values(field).annotate(n=Count('pk')):
                usage[row[field]] += row['n']

        total_removed = 0
        self.stdout.write('')

        for key, subjects in sorted(duplicate_groups.items()):
            # Keep the most-referenced row; tie-break on the oldest (lowest pk).
            subjects.sort(key=lambda s: (-usage[s.pk], s.pk))
            keeper, dupes = subjects[0], subjects[1:]

            self.stdout.write(self.style.WARNING(f'"{key}"'))
            self.stdout.write(
                f'  KEEP   [{keeper.code}] {keeper.name} '
                f'(full marks {keeper.full_marks}, {usage[keeper.pk]} reference(s))'
            )
            for dupe in dupes:
                warn = ''
                if dupe.full_marks != keeper.full_marks:
                    warn = self.style.ERROR(
                        f'  <-- full marks differ ({dupe.full_marks} vs {keeper.full_marks}), check before applying'
                    )
                self.stdout.write(
                    f'  MERGE  [{dupe.code}] {dupe.name} '
                    f'({usage[dupe.pk]} reference(s)){warn}'
                )

            if apply_changes:
                with transaction.atomic():
                    for dupe in dupes:
                        # Repoint references at the keeper. Where a unique
                        # constraint would be violated the keeper already has
                        # the equivalent row, so the duplicate one is dropped.
                        for mark in ExamMark.objects.filter(subject=dupe):
                            if ExamMark.objects.filter(
                                exam_id=mark.exam_id, student_id=mark.student_id,
                                subject=keeper,
                            ).exists():
                                mark.delete()
                            else:
                                mark.subject = keeper
                                mark.save(update_fields=['subject'])

                        for req in SubjectRequirement.objects.filter(subject=dupe):
                            if SubjectRequirement.objects.filter(
                                institution_id=req.institution_id,
                                admission_class=req.admission_class,
                                group=req.group,
                                subject=keeper,
                            ).exists():
                                req.delete()
                            else:
                                req.subject = keeper
                                req.save(update_fields=['subject'])

                        for setting in SubjectMarkSetting.objects.filter(subject=dupe):
                            if SubjectMarkSetting.objects.filter(
                                institution_id=setting.institution_id,
                                admission_class=setting.admission_class,
                                exam_type=setting.exam_type,
                                subject=keeper,
                            ).exists():
                                setting.delete()
                            else:
                                setting.subject = keeper
                                setting.save(update_fields=['subject'])

                        StudentSubject.objects.filter(subject=dupe).update(subject=keeper)
                        dupe.delete()
                        total_removed += 1
            else:
                total_removed += len(dupes)

            self.stdout.write('')

        if apply_changes:
            self.stdout.write(self.style.SUCCESS(
                f'Merged and removed {total_removed} duplicate subject(s).'
            ))
        else:
            self.stdout.write(self.style.NOTICE(
                f'DRY RUN: {total_removed} duplicate subject(s) would be removed. '
                'Re-run with --apply to perform the merge.'
            ))
