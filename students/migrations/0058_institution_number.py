"""Give every institution its own number, and re-number teachers with it.

The owner's list is *College 1, School 2, Shishukanon 3, Madrasa 4*: the branch
number is part of the teacher number (``2011 02 0001`` = School 2's first
teacher) and each branch counts its own teachers from 1.

Teachers numbered before this migration hold ``2011 000 001`` (year + one global
serial), so they are renumbered here, in join-date order inside each branch, and
the per-branch counters are seeded to the highest serial handed out so a number
is never reused.
"""
from django.db import migrations, models


YEAR_PREFIX = '2011'
BRANCH_WIDTH = 2
SERIAL_WIDTH = 4


def _format(serial, branch):
    return f'{YEAR_PREFIX}{branch:0{BRANCH_WIDTH}d}{serial:0{SERIAL_WIDTH}d}'


def forwards(apps, schema_editor):
    Institution = apps.get_model('students', 'Institution')
    Employee = apps.get_model('students', 'Employee')
    DocumentSequence = apps.get_model('students', 'DocumentSequence')

    # 1. Number the existing branches in the order they were created — that is
    #    the order the owner listed them in (College 1, School 2, …).
    used = set()
    for institution in Institution.objects.order_by('pk'):
        branch = institution.number
        if branch is None:
            branch = next(
                (candidate for candidate in range(1, 100) if candidate not in used),
                None,
            )
            if branch is None:
                continue
            institution.number = branch
            institution.save(update_fields=['number'])
        used.add(branch)

    # 2. Re-number the teachers branch by branch, oldest appointment first, and
    #    lift each branch's counter past the highest serial it handed out.
    for institution in Institution.objects.exclude(number__isnull=True):
        teachers = (
            Employee.objects.filter(institution=institution, teacher_no__isnull=False)
            .exclude(teacher_no='')
            .order_by('join_date', 'pk')
        )
        highest = 0
        for serial, teacher in enumerate(teachers, start=1):
            teacher.teacher_no = _format(serial, institution.number)
            teacher.save(update_fields=['teacher_no'])
            highest = serial
        DocumentSequence.objects.update_or_create(
            scope=f'TEACHER-{institution.number:02d}',
            defaults={'last_number': highest},
        )

    # 3. A teaching employee with no institution cannot carry a branch number;
    #    clear it so the picker never offers a number nobody can explain.
    Employee.objects.filter(
        institution__isnull=True, teacher_no__isnull=False
    ).exclude(teacher_no='').update(teacher_no=None)


def backwards(apps, schema_editor):
    # Numbers are printed on paper: going back to the old global serial would
    # hand out duplicates, so the numbers stay as they are. Only the new
    # institution column is emptied by the reverse schema operation.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('students', '0057_employee_teacher_no_null_blank'),
    ]

    operations = [
        migrations.AddField(
            model_name='institution',
            name='number',
            field=models.PositiveSmallIntegerField(
                blank=True,
                help_text=(
                    'The running number the owner uses for this branch — College 1, '
                    'School 2, Shishukanon 3, Madrasa 4. It becomes the middle part of '
                    'every teacher number here (2011 02 0001).'
                ),
                null=True,
                unique=True,
                verbose_name='Institution number',
            ),
        ),
        migrations.RunPython(forwards, backwards),
    ]
