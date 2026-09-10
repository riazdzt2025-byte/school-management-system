"""The Guardian Contact Number is required for students too.

Since the unification, guardian_contact_no is the one primary contact for a
student. It used to be optional at the model level (the old form had a
separate "Student's Contact No." box); the office now always records the
guardian number when adding or editing a student, and the Excel import
rejects rows without one.

State-only change (blank is a form-layer rule, not a database constraint) —
existing rows are untouched; editing one of them simply asks for the number.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('students', '0040_drop_legacy_contact_columns'),
    ]

    operations = [
        migrations.AlterField(
            model_name='student',
            name='guardian_contact_no',
            field=models.CharField(help_text="Guardian's primary contact number, e.g. 01812345678. Stored as text so the leading zero is kept.", max_length=20),
        ),
    ]
