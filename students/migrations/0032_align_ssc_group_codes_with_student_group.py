"""Map the legacy SSC board group codes onto Student.GROUP_CHOICES.

SSCRegistration kept its own group codes ('SCIENCE', 'COMMERCE', 'ARTS') while
every other screen stores 'SCI', 'BUS', 'HUM'. Nothing could be joined between
the two: filtering SSC registrations by a student's group returned an empty
list, and comparing a board entry against the school record always disagreed.
"""
from django.db import migrations, models

LEGACY_TO_SHARED = {
    'SCIENCE': 'SCI',
    'COMMERCE': 'BUS',
    'ARTS': 'HUM',
    # Written by an early version of the Excel importer.
    'SCIENCE ': 'SCI',
}


def forwards(apps, schema_editor):
    SSCRegistration = apps.get_model('students', 'SSCRegistration')
    for legacy_code, shared_code in LEGACY_TO_SHARED.items():
        SSCRegistration.objects.filter(group=legacy_code).update(group=shared_code)


def backwards(apps, schema_editor):
    SSCRegistration = apps.get_model('students', 'SSCRegistration')
    for shared_code, legacy_code in (('SCI', 'SCIENCE'), ('BUS', 'COMMERCE'), ('HUM', 'ARTS')):
        SSCRegistration.objects.filter(group=shared_code).update(group=legacy_code)


class Migration(migrations.Migration):

    dependencies = [
        ('students', '0031_add_practical_weekly_and_pass_rules'),
    ]

    operations = [
        # Data first: rows still holding 'SCIENCE' would not validate against the
        # new choices, and max_length has to stay wide enough for them until they
        # are rewritten.
        migrations.RunPython(forwards, backwards),
        migrations.AlterField(
            model_name='sscregistration',
            name='group',
            field=models.CharField(
                choices=[('SCI', 'Science'), ('BUS', 'Business Studies'), ('HUM', 'Humanities')],
                max_length=10,
            ),
        ),
    ]
