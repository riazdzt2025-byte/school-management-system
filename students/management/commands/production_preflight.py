"""``manage.py production_preflight`` — নীল/সবুজ তালিকা, লাইভে যাওয়ার আগে।

ব্যবহার::

    python manage.py production_preflight              # warn থাকলেও 0
    python manage.py production_preflight --fail-on-warn   # warn হলেও 1

প্রতিটি সারি একটি বাস্তব ঝুঁকির জন্য, যেটি বুটের সময় কোনো এরর দেয় না —
কিন্তু লাইভে গেলে চুপচাপ ক্ষতি করে (DEBUG=True, ফাঁকা ALLOWED_HOSTS,
ফাইল লোকাল ডিস্কে, ব্যাকআপ নেই, static manifest নেই)।

টেস্ট: ``students/test_production_preflight.py`` — সেখানে যুক্তি
(``students/preflight.py``) আলাদাভাবে যাচাই করা হয়, ক্লাউড অ্যাকাউন্ট ছাড়াই।
"""
import sys

from django.core.management.base import BaseCommand

from students import preflight

SYMBOL = {preflight.OK: '\033[32m✔\033[0m',
          preflight.WARN: '\033[33m!\033[0m',
          preflight.FAIL: '\033[31m✘\033[0m'}


class Command(BaseCommand):
    help = 'প্রোডাকশনে যাওয়ার আগে প্রয়োজনীয় সেটিংস, ডেটাবেস, স্টোরেজ ও ব্যাকআপ যাচাই করে।'

    def add_arguments(self, parser):
        parser.add_argument(
            '--fail-on-warn', action='store_true',
            help='সতর্কবার্তা (warn) থাকলেও নন-জিরো exit code দেবে।',
        )

    def handle(self, *args, **options):
        checks = preflight.evaluate_checks(**preflight.collect_environment())
        # Django's BaseCommand already defines --no-color, so it is read here
        # rather than re-declared (re-declaring raises an argparse conflict).
        use_color = not options.get('no_color', False)

        self.stdout.write('\nপ্রোডাকশন প্রিফ্লাইট\n' + '=' * 46)
        for check in checks:
            mark = SYMBOL[check.status] if use_color else check.status.upper()
            self.stdout.write(f'{mark}  {check.title}')
            self.stdout.write(f'      {check.detail}')

        fails = [c for c in checks if c.status == preflight.FAIL]
        warns = [c for c in checks if c.status == preflight.WARN]
        self.stdout.write('=' * 46)
        self.stdout.write(
            f'মোট {len(checks)}টি যাচাই · ঠিক {len(checks) - len(fails) - len(warns)} · '
            f'সতর্কতা {len(warns)} · সমস্যা {len(fails)}'
        )

        if fails:
            self.stdout.write(self.style.ERROR(
                '\nলাইভে যাওয়ার আগে "সমস্যা" সারিগুলো ঠিক করতে হবে।'
            ))
            sys.exit(1)
        if warns and options['fail_on_warn']:
            self.stdout.write(self.style.WARNING(
                '\n--fail-on-warn দেওয়া আছে, তাই সতর্কতাগুলোও ব্লক করছে।'
            ))
            sys.exit(1)
        if warns:
            self.stdout.write(self.style.WARNING(
                '\nকোনো কঠিন সমস্যা নেই। সতর্কতাগুলো ইচ্ছাকৃত ছাড় হলে ঠিক আছে — '
                'নাহলে এক এক করে ঠিক করুন (docs/POSTGRES_S3_BACKUP_SETUP_BN.md)।'
            ))
        else:
            self.stdout.write(self.style.SUCCESS('\nসব ঠিক — লাইভে যাওয়ার জন্য প্রস্তুত।'))
