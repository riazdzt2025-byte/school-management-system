"""Drop the legacy contact columns now that guardian_contact_no is the single
canonical contact number ("Guardian Contact Number / অভিভাবকের যোগাযোগ নম্বর").

Approved in this session. Safety sequence inside this migration:

1. Backfill — same rule as 0039: where the guardian number is blank and the
   legacy column holds a number, the legacy number is copied across. This
   catches rows created after 0039 ran (e.g. hand-edited in the admin).
2. Archive — every row whose legacy number DIFFERS from its guardian number
   is written to AuditLog (action 'legacy_contact_dropped') before the
   column disappears. A legacy number is therefore never silently lost and
   can be restored by editing the record's guardian contact.
3. RemoveField — Student.contact_no and
   AdmissionApplication.applicant_contact_no are dropped.

Reverse re-creates the columns empty; the archived values live on in
AuditLog.
"""
from django.db import migrations, models
from django.db.models import Q


def archive_and_drop_legacy_contacts(apps, schema_editor):
    Student = apps.get_model('students', 'Student')
    AdmissionApplication = apps.get_model('students', 'AdmissionApplication')
    AuditLog = apps.get_model('students', 'AuditLog')

    guardian_empty = Q(guardian_contact_no='') | Q(guardian_contact_no__isnull=True)

    def legacy_set(field):
        return ~Q(**{field: ''}) & ~Q(**{f'{field}__isnull': True})

    def backfill(model, legacy_field):
        """Fill a blank guardian number from the legacy column (never the
        other way round, never over an existing guardian number)."""
        rows = model.objects.filter(guardian_empty & legacy_set(legacy_field))
        for row in rows.iterator():
            row.guardian_contact_no = getattr(row, legacy_field)
            row.save(update_fields=['guardian_contact_no'])

    def archive(model, legacy_field, model_label, row_key, row_name):
        """Audit-log every row that would lose a legacy number differing from
        its guardian number when the column is dropped."""
        dropped = []
        for row in model.objects.filter(legacy_set(legacy_field)).iterator():
            legacy = (getattr(row, legacy_field) or '').strip()
            guardian = (row.guardian_contact_no or '').strip()
            if legacy and guardian and legacy != guardian:
                dropped.append({
                    'identifier': row_key(row),
                    'name': row_name(row),
                    'legacy_contact': legacy,
                    'guardian_contact': guardian,
                })
        if dropped:
            AuditLog.objects.create(
                action='legacy_contact_dropped',
                model_name=model_label,
                object_repr=(
                    f'{len(dropped)} row(s) kept a different legacy contact '
                    'number before the column was removed'
                ),
                details={
                    'dropped_rows': dropped,
                    'kept': 'guardian_contact_no',
                    'note': (
                        'The legacy contact column was removed by migration '
                        'students.0040. The guardian contact number was kept '
                        'as the single primary contact. If one of the legacy '
                        'numbers was the correct one, edit the record and '
                        'paste it into the Guardian Contact Number field.'
                    ),
                },
            )
        return len(dropped)

    backfill(Student, 'contact_no')
    backfill(AdmissionApplication, 'applicant_contact_no')
    archive(Student, 'contact_no', 'Student',
            lambda s: s.student_id or str(s.pk), lambda s: s.name)
    archive(AdmissionApplication, 'applicant_contact_no', 'AdmissionApplication',
            lambda a: a.application_number or str(a.pk),
            lambda a: a.applicant_name)


class Migration(migrations.Migration):

    dependencies = [
        ('students', '0039_unify_guardian_contact'),
    ]

    operations = [
        # Runs before the RemoveFields below, inside the same transaction.
        migrations.RunPython(
            archive_and_drop_legacy_contacts,
            migrations.RunPython.noop,
        ),
        migrations.RemoveField(
            model_name='student',
            name='contact_no',
        ),
        migrations.RemoveField(
            model_name='admissionapplication',
            name='applicant_contact_no',
        ),
    ]
