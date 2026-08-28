from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
from django.core.serializers.json import DjangoJSONEncoder


class Migration(migrations.Migration):
    dependencies = [
        ('students', '0012_admissionapplication'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='AuditLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('action', models.CharField(max_length=100)),
                ('model_name', models.CharField(max_length=100)),
                ('object_id', models.CharField(blank=True, max_length=100)),
                ('object_repr', models.CharField(blank=True, max_length=255)),
                ('timestamp', models.DateTimeField(auto_now_add=True)),
                ('snapshot', models.JSONField(default=dict, encoder=DjangoJSONEncoder)),
                ('details', models.JSONField(default=dict, encoder=DjangoJSONEncoder)),
                ('actor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='audit_logs', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-timestamp', '-id']},
        ),
        migrations.CreateModel(
            name='PromotionBatch',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('session', models.CharField(max_length=20)),
                ('from_class', models.CharField(max_length=10)),
                ('from_section', models.CharField(blank=True, max_length=5)),
                ('to_class', models.CharField(max_length=10)),
                ('to_section', models.CharField(blank=True, max_length=5)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('rolled_back_at', models.DateTimeField(blank=True, null=True)),
                ('actor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='promotion_batches', to=settings.AUTH_USER_MODEL)),
                ('rollback_actor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='promotion_rollbacks', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-created_at', '-id']},
        ),
        migrations.CreateModel(
            name='StudentPromotionHistory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('source_class', models.CharField(max_length=10)),
                ('source_section', models.CharField(blank=True, max_length=5)),
                ('target_class', models.CharField(max_length=10)),
                ('target_section', models.CharField(blank=True, max_length=5)),
                ('promoted_at', models.DateTimeField(auto_now_add=True)),
                ('rolled_back_at', models.DateTimeField(blank=True, null=True)),
                ('batch', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='student_history', to='students.promotionbatch')),
                ('student', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='promotion_history', to='students.student')),
            ],
            options={'ordering': ['student__name', 'id'], 'constraints': [models.UniqueConstraint(fields=('batch', 'student'), name='unique_promotion_batch_student')]},
        ),
    ]