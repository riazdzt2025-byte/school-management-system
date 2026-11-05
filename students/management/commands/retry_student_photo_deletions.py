"""Process the durable student-photo deletion outbox."""
from django.core.management.base import BaseCommand, CommandError

from students.photo_deletion import process_due_student_photo_deletions


class Command(BaseCommand):
    help = (
        'Delete due student-photo objects from configured storage. Failed jobs '
        'remain in the database and are retried with exponential backoff.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            default=100,
            help='Maximum due jobs to process in one run (default: 100).',
        )
        parser.add_argument(
            '--database',
            default='default',
            help='Database alias containing the deletion outbox (default: default).',
        )

    def handle(self, *args, **options):
        limit = options['limit']
        if limit < 1 or limit > 1000:
            raise CommandError('--limit must be between 1 and 1000.')

        result = process_due_student_photo_deletions(
            limit=limit,
            using=options['database'],
        )
        self.stdout.write(
            'Student photo deletion jobs: '
            f"processed={result['processed']}, deleted={result['deleted']}, "
            f"retrying={result['retrying']}."
        )
        if result['retrying']:
            raise CommandError(
                f"{result['retrying']} deletion job(s) failed; durable retries were scheduled."
            )
