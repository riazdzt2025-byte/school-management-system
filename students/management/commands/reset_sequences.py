"""``manage.py reset_sequences`` — fixture লোড করার পরে Postgres-এর ID ফাঁদ সারায়।

কেন দরকার
---------
SQLite থেকে Postgres-এ ডেটা নেওয়ার প্রমাণিত পথ: SQLite-এ ``dumpdata`` →
Postgres-এ ``migrate`` → ``loaddata``। কিন্তু ``loaddata`` প্রতিটি সারিকে *আসল*
আইডি (PK) দিয়ে বসায়, আর Postgres-এর ``id`` কলামের sequence তখনো ১ থেকে শুরু —
তাই **পরের নতুন শিক্ষার্থী যোগ করলেই** ``duplicate key value violates unique
constraint`` আসে। অ্যাপ ঠিক থাকে, ডেটা ঠিক থাকে, শুধু নতুন সারি যোগ করা যায় না।

এই কমান্ড Django-র নিজের ``sqlsequencereset`` থেকে SQL নিয়ে প্রতিটি টেবিলের
sequence আসল সর্বোচ্চ আইডিতে সেট করে দেয়।

ব্যবহার::

    python manage.py reset_sequences --dry-run     # আগে দেখে নিন
    python manage.py reset_sequences               # প্রয়োগ

SQLite-এ এটি কিছু করে না (AUTOINCREMENT নিজেই সামলায়) — তাই বারবার চালালেও নিরাপদ।
"""
from django.apps import apps
from django.core.management.base import BaseCommand
from django.core.management.color import no_style
from django.db import connection


class Command(BaseCommand):
    help = (
        'Postgres-এর sequence গুলো টেবিলের সর্বোচ্চ আইডিতে সেট করে '
        '(fixture loaddata করার পরে অবশ্যই একবার চালান)।'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='SQL চালাবে না, শুধু দেখাবে।',
        )
        parser.add_argument(
            '--app', action='append', default=None,
            help='শুধু এই অ্যাপের মডেলগুলো (একাধিকবার দেওয়া যায়), যেমন: --app students',
        )

    def handle(self, *args, **options):
        if connection.vendor != 'postgresql':
            self.stdout.write(
                f'ডেটাবেস: {connection.vendor} — sequence ঠিক করার দরকার নেই '
                '(SQLite নিজেই AUTOINCREMENT সামলায়)।'
            )
            return

        wanted = set(options.get('app') or [])
        models = [
            model for model in apps.get_models()
            if not wanted or model._meta.app_label in wanted
        ]
        statements = connection.ops.sequence_reset_sql(no_style(), models)

        if not statements:
            self.stdout.write(self.style.WARNING(
                'কোনো sequence SQL পাওয়া গেল না — মডেল খুঁজে পাননি? '
                '(--app দিয়ে সীমিত করেছেন?)'
            ))
            return

        if options['dry_run']:
            self.stdout.write(f'{len(statements)}টি statement (dry-run, কিছু বদলায়নি):\n')
            for statement in statements:
                self.stdout.write(f'  {statement}')
            return

        with connection.cursor() as cursor:
            for statement in statements:
                cursor.execute(statement)

        self.stdout.write(self.style.SUCCESS(
            f'{len(statements)}টি sequence ঠিক করা হয়েছে — এখন নতুন সারি যোগ করলে '
            'আইডি সংঘর্ষ হবে না।'
        ))
