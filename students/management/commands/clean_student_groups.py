"""
python manage.py clean_student_groups            # dry run, changes nothing
python manage.py clean_student_groups --apply    # actually clear the groups

Groups only exist from class 9 upwards (SSC 9-10, HSC 11-12). Primary and
junior secondary students (Shishu-5 and 6-8) follow one common syllabus, so a
group stored on them is simply wrong — it makes the student list, the marks
entry and the result sheets filter on a group those classes never had.

The report lists every affected class before anything is touched, so run it
without --apply first and read the numbers.
"""
from collections import Counter

from django.core.management.base import BaseCommand

from students.models import Student, class_supports_group


class Command(BaseCommand):
    help = (
        "Clear the group on students whose class has no group (below class 9). "
        "Dry run by default; pass --apply to write."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply', action='store_true',
            help='Actually clear the groups. Without it nothing is changed.',
        )

    def handle(self, *args, **options):
        apply_changes = options['apply']

        affected = [
            student for student in Student.objects.exclude(group='').only(
                'id', 'student_id', 'name', 'admission_class', 'group',
            )
            if not class_supports_group(student.admission_class)
        ]

        if not affected:
            self.stdout.write(self.style.SUCCESS(
                'Nothing to clean: no student below class 9 has a group.'
            ))
            return

        by_class = Counter(str(s.admission_class).strip() for s in affected)
        by_group = Counter(s.group for s in affected)

        self.stdout.write(f'{len(affected)} student(s) below class 9 carry a group:\n')
        for cls, count in sorted(by_class.items(), key=lambda item: item[0].zfill(3)):
            self.stdout.write(f'  class {cls}: {count} student(s)')
        self.stdout.write('')
        for code, count in sorted(by_group.items()):
            label = dict(Student.GROUP_CHOICES).get(code, code)
            self.stdout.write(f'  {code} ({label}): {count}')

        if not apply_changes:
            self.stdout.write('\nDry run — nothing was changed. Re-run with --apply to clear these groups.')
            return

        ids = [s.id for s in affected]
        cleared = Student.objects.filter(id__in=ids).update(group='')
        self.stdout.write(self.style.SUCCESS(
            f'Cleared the group on {cleared} student(s). Classes 9-12 were left untouched.'
        ))
