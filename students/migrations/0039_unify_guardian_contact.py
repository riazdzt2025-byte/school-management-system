"""One primary contact per student / admission application.

The guardian_contact_no column becomes the single canonical contact number
("Guardian Contact Number / অভিভাবকের যোগাযোগ নম্বর"). The legacy
Student.contact_no and AdmissionApplication.applicant_contact_no columns
stay in place — only marked legacy — until any conflicting data has been
reviewed by a human, so nothing is silently lost.

The data step below copies the legacy number into guardian_contact_no ONLY
where the guardian number is blank, so an existing guardian number is never
overwritten. Rows where both columns hold a different number are left
untouched; the read-only `contact_conflict_report` management command lists
them for a manual decision.
"""
from django.db import migrations, models
from django.db.models import Q


def backfill_guardian_contact_from_legacy(apps, schema_editor):
    Student = apps.get_model('students', 'Student')
    AdmissionApplication = apps.get_model('students', 'AdmissionApplication')

    # guardian blank (or NULL from a raw load) AND a non-blank legacy number.
    guardian_empty = Q(guardian_contact_no='') | Q(guardian_contact_no__isnull=True)
    legacy_set = ~Q(contact_no='') & ~Q(contact_no__isnull=True)

    for student in Student.objects.filter(guardian_empty & legacy_set).iterator():
        student.guardian_contact_no = student.contact_no
        student.save(update_fields=['guardian_contact_no'])

    applicant_set = ~Q(applicant_contact_no='') & ~Q(applicant_contact_no__isnull=True)
    for application in (AdmissionApplication.objects
                        .filter(guardian_empty & applicant_set).iterator()):
        application.guardian_contact_no = application.applicant_contact_no
        application.save(update_fields=['guardian_contact_no'])


class Migration(migrations.Migration):

    dependencies = [
        ('students', '0038_fee'),
    ]

    operations = [
        migrations.AlterField(
            model_name='admissionapplication',
            name='applicant_contact_no',
            field=models.CharField(blank=True, help_text='Legacy column — no longer collected. Kept until old data is merged into guardian_contact_no.', max_length=20),
        ),
        migrations.AlterField(
            model_name='admissionapplication',
            name='guardian_contact_no',
            field=models.CharField(help_text="Guardian's primary contact number, e.g. 01812345678. Stored as text so the leading zero is kept.", max_length=20),
        ),
        migrations.AlterField(
            model_name='student',
            name='contact_no',
            field=models.CharField(blank=True, help_text='Legacy column — no longer collected. Kept until old data is merged into guardian_contact_no.', max_length=20),
        ),
        migrations.AlterField(
            model_name='student',
            name='guardian_contact_no',
            field=models.CharField(blank=True, help_text="Guardian's primary contact number, e.g. 01812345678. Stored as text so the leading zero is kept.", max_length=20),
        ),
        # Safe by construction: only fills blank guardian numbers, never
        # overwrites one. Conflicting rows are skipped for human review.
        #
        # Reversal is a no-op on purpose: once a blank guardian number has
        # been filled from the legacy column, the migration cannot know
        # which values it wrote, so un-applying would risk wiping real data.
        migrations.RunPython(
            backfill_guardian_contact_from_legacy,
            migrations.RunPython.noop,
        ),
    ]
