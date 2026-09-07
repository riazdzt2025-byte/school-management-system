"""Groups only exist from class 9 upwards.

Older screens offered a group for every class, so students in class 6-8 (and
primary) ended up with "Science" stored against them. Those rows are cleared
here — the same thing `python manage.py clean_student_groups --apply` does,
run automatically on deploy so the fix does not depend on someone remembering
to open a shell.

No schema change, so this is reversible and safe to re-run.
"""
from django.db import migrations


# Kept as literals on purpose: a data migration must not import model code
# that keeps changing.
GROUPED_CLASSES = {'9', '10', '11', '12'}


def _normalize(value):
    label = str(value or '').strip().lower()
    if label.isdigit():
        label = str(int(label))
    return label


def clear_groups_below_class_9(apps, schema_editor):
    Student = apps.get_model('students', 'Student')
    affected = [
        student.id
        for student in Student.objects.exclude(group='').only('id', 'admission_class')
        if _normalize(student.admission_class) not in GROUPED_CLASSES
    ]
    if affected:
        Student.objects.filter(id__in=affected).update(group='')


def noop_reverse(apps, schema_editor):
    # The cleared values are not recoverable, and re-adding a wrong group
    # would be worse than leaving it blank.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('students', '0032_align_ssc_group_codes_with_student_group'),
    ]

    operations = [
        migrations.RunPython(clear_groups_below_class_9, noop_reverse),
    ]
