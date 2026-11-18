"""Updated help text for the teacher number (year + branch + branch serial).

Only the help text changed; behaviour lives in models.Employee.save().
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('students', '0058_institution_number'),
    ]

    operations = [
        migrations.AlterField(
            model_name='employee',
            name='teacher_no',
            field=models.CharField(blank=True, help_text="Founding year (2011) + the institution number + that branch's own serial, e.g. 2011 02 0001 for School 2's first teacher. Left blank, the next free number for the employee's institution is allocated on save.", max_length=20, null=True, unique=True, verbose_name='Teacher number'),
        ),
    ]
