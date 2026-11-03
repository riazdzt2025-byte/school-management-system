# Data migration: set default display_order for common subjects
# based on the NCTB standard subject serial for classes 6-10.

from django.db import migrations


SUBJECT_ORDER = [
    # (code pattern, display_order)
    # 1. বাংলা ১ম পত্র
    ('BAN 1ST', 10),
    ('BAN1', 10),
    ('BAN-1ST', 10),
    ('BAN1ST', 10),
    # 2. বাংলা ২য় পত্র
    ('BAN 2ND', 20),
    ('BAN2', 20),
    ('BAN-2ND', 20),
    ('BAN2ND', 20),
    # 3. ইংরেজি ১ম পত্র
    ('ENG 1ST', 30),
    ('ENG1', 30),
    ('ENG-1ST', 30),
    ('ENG1ST', 30),
    # 4. ইংরেজি ২য় পত্র
    ('ENG 2ND', 40),
    ('ENG2', 40),
    ('ENG-2ND', 40),
    ('ENG2ND', 40),
    # 5. গণিত
    ('MATH', 50),
    ('GANIT', 50),
    # 6. কৃষিশিক্ষা
    ('AGRI', 60),
    ('KRISHI', 60),
    # 7. ধর্ম ও নৈতিক শিক্ষা
    ('REL', 70),
    ('RELIGION', 70),
    ('ISLAM', 70),
    ('HINDU', 71),
    ('CHRISTIAN', 72),
    ('BUDDHIST', 73),
    # 8. বিজ্ঞান
    ('SCI', 80),
    ('BIGGAN', 80),
    # 9. বাংলাদেশ ও বিশ্বপরিচয়
    ('BWO', 90),
    ('BANGLADESH', 90),
    # 10. তথ্য ও যোগাযোগ প্রযুক্তি
    ('ICT', 100),
    ('IT', 100),
    # Additional common subjects (higher orders so they come after the main 10)
    ('PHY', 110),
    ('PHYSICS', 110),
    ('CHEM', 120),
    ('CHEMISTRY', 120),
    ('BIO', 130),
    ('BIOLOGY', 130),
    ('HIGHER MATH', 140),
    ('HMATH', 140),
    ('H-MATH', 140),
    ('ACC', 150),
    ('ACCOUNTING', 150),
    ('BUS', 160),
    ('BUSINESS', 160),
    ('ECO', 170),
    ('ECONOMICS', 170),
    ('FIN', 180),
    ('FINANCE', 180),
    ('SOC', 190),
    ('SOCIOLOGY', 190),
    ('HIS', 200),
    ('HISTORY', 200),
    ('GEO', 210),
    ('GEOGRAPHY', 210),
    ('STAT', 220),
    ('STATISTICS', 220),
    ('CIV', 230),
    ('CIVICS', 230),
]


def set_display_order(apps, schema_editor):
    Subject = apps.get_model('students', 'Subject')
    code_upper = {}
    for code_pattern, order in SUBJECT_ORDER:
        code_upper[code_pattern.upper()] = order

    next_order = 300  # for subjects not in the predefined list
    for subject in Subject.objects.all().order_by('code'):
        subject_code_upper = subject.code.upper().strip()
        matched_order = None
        # Exact match first
        if subject_code_upper in code_upper:
            matched_order = code_upper[subject_code_upper]
        else:
            # Partial match - check if code starts with any known pattern
            for pattern, order in sorted(code_upper.items(), key=lambda x: len(x[0]), reverse=True):
                if subject_code_upper.startswith(pattern):
                    matched_order = order
                    break
        if matched_order is not None:
            subject.display_order = matched_order
        else:
            subject.display_order = next_order
            next_order += 10
        subject.save(update_fields=['display_order'])


def reverse_display_order(apps, schema_editor):
    # No-op reverse: we don't zero out, just leave as is
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('students', '0053_add_subject_display_order'),
    ]

    operations = [
        migrations.RunPython(set_display_order, reverse_display_order),
    ]
