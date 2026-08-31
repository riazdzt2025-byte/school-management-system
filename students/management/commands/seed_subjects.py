from django.core.management.base import BaseCommand
from students.models import Subject
from students.curriculum_data import SUBJECTS


class Command(BaseCommand):
    help = "Load the pre-loaded Bangladesh-curriculum subject list into the Subject master list."

    def handle(self, *args, **options):
        created, skipped = 0, 0
        for code, name, full_marks, category in SUBJECTS:
            _, was_created = Subject.objects.get_or_create(
                code=code,
                defaults={'name': name, 'full_marks': full_marks, 'category': category},
            )
            if was_created:
                created += 1
            else:
                skipped += 1
        self.stdout.write(self.style.SUCCESS(
            f"Seed complete: {created} subject(s) created, {skipped} already existed."
        ))
