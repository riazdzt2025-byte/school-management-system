"""Give a teacher a login account, and add the Teacher department.

``Employee.user`` is the link that decides whose classes a signed-in teacher
may open; the department choice only adds the login tile.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('students', '0060_mark_correction_request'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='employee',
            name='user',
            field=models.OneToOneField(blank=True, help_text='Give a teacher a login so they can enter marks and check the correction applications filed about their own classes.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='employee_profile', to=settings.AUTH_USER_MODEL, verbose_name='Login account'),
        ),
        migrations.AlterField(
            model_name='institutionaccess',
            name='department',
            field=models.CharField(choices=[('Office', 'Office'), ('Exam', 'Exam'), ('Accounts', 'Accounts'), ('Teacher', 'Teacher')], max_length=30),
        ),
    ]
