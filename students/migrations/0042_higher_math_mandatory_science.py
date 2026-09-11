from django.db import migrations


def make_ssc_science_higher_math_mandatory(apps, schema_editor):
    """Align existing SSC Science assignments with the built-in curriculum.

    This deliberately only changes Higher Mathematics for classes 9/10 (with
    legacy zero-padded spellings). Biology and all HSC/Business rows remain
    untouched.
    """
    SubjectRequirement = apps.get_model('students', 'SubjectRequirement')
    SubjectRequirement.objects.filter(
        admission_class__in=['9', '09', '10'],
        group='SCI',
        subject__code='HMATH',
    ).update(requirement_type='MANDATORY', optional_set_key='')


def reverse_ssc_science_higher_math(apps, schema_editor):
    SubjectRequirement = apps.get_model('students', 'SubjectRequirement')
    SubjectRequirement.objects.filter(
        admission_class__in=['9', '09', '10'],
        group='SCI',
        subject__code='HMATH',
        requirement_type='MANDATORY',
    ).update(requirement_type='OPTIONAL', optional_set_key='sci_4th')


class Migration(migrations.Migration):
    dependencies = [('students', '0041_student_guardian_contact_required')]
    operations = [migrations.RunPython(
        make_ssc_science_higher_math_mandatory,
        reverse_ssc_science_higher_math,
    )]
