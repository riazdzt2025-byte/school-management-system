"""Mark correction requests: the printed, signed workflow the exam dept owns.

A requested mark lives in this table only — no result sheet reads it — until an
exam-department approval writes it into ExamMark.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('students', '0059_alter_employee_teacher_no_help'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='MarkCorrectionRequest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('kind', models.CharField(choices=[('MARKS', 'Subject mark correction')], default='MARKS', max_length=20)),
                ('admission_class', models.CharField(max_length=10)),
                ('section', models.CharField(blank=True, max_length=5)),
                ('group', models.CharField(blank=True, max_length=5)),
                ('current_total', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ('current_parts', models.JSONField(blank=True, default=dict)),
                ('requested_total', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ('requested_parts', models.JSONField(blank=True, default=dict)),
                ('reason', models.TextField(help_text='Why the mark changes — printed on the signed application.')),
                ('status', models.CharField(choices=[('DRAFT', 'Draft — with the office'), ('SUBMITTED', 'Submitted — awaiting exam department'), ('APPROVED', 'Approved'), ('REJECTED', 'Rejected'), ('WITHDRAWN', 'Withdrawn')], default='DRAFT', max_length=12)),
                ('filed_at', models.DateTimeField(blank=True, null=True)),
                ('submitted_at', models.DateTimeField(blank=True, null=True)),
                ('teacher_note', models.CharField(blank=True, max_length=200)),
                ('decided_at', models.DateTimeField(blank=True, null=True)),
                ('decision_reason', models.TextField(blank=True, help_text='Required when a request is rejected.')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('decided_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='mark_correction_requests_decided', to=settings.AUTH_USER_MODEL)),
                ('exam', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='mark_correction_requests', to='students.exam')),
                ('filed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='mark_correction_requests_filed', to=settings.AUTH_USER_MODEL)),
                ('institution', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='mark_correction_requests', to='students.institution')),
                ('student', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='mark_correction_requests', to='students.student')),
                ('subject', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='mark_correction_requests', to='students.subject')),
                ('submitted_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='mark_correction_requests_submitted', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at', '-pk'],
                'constraints': [models.UniqueConstraint(condition=models.Q(('status__in', ['APPROVED', 'REJECTED', 'WITHDRAWN']), _negated=True), fields=('exam', 'student', 'subject'), name='unique_open_mark_correction')],
            },
        ),
    ]
