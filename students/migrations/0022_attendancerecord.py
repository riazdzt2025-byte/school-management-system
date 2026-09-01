from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('students', '0021_studentpromotionhistory_source_roll_no'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='AttendanceRecord',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField()),
                ('status', models.CharField(choices=[('P', 'Present'), ('A', 'Absent'), ('L', 'Late'), ('H', 'Holiday')], default='P', max_length=1)),
                ('remarks', models.CharField(blank=True, max_length=200)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='attendance_records_created', to=settings.AUTH_USER_MODEL)),
                ('employee', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='attendance_records', to='students.employee')),
                ('institution', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='attendance_records', to='students.institution')),
                ('student', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='attendance_records', to='students.student')),
            ],
            options={
                'ordering': ['-date', '-created_at'],
                'constraints': [
                    models.UniqueConstraint(condition=models.Q(('student__isnull', False)), fields=('institution', 'student', 'date'), name='unique_student_attendance_per_day'),
                    models.UniqueConstraint(condition=models.Q(('employee__isnull', False)), fields=('institution', 'employee', 'date'), name='unique_employee_attendance_per_day'),
                ],
            },
        ),
    ]
