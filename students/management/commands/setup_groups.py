"""
python manage.py setup_groups

Django Groups + Permissions তৈরি করে ডিপার্টমেন্ট-ওয়াইজ এক্সেসের জন্য।
প্রতিটা group নিজের মডেলে add/change/delete পায়, বাকি সব মডেলে শুধু view পায়।
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from students.models import (
    Student, Subject, TransferCertificate, Certificate,
    SSCRegistration, BoardResult,
    Exam, ExamMark, SeatPlan, Employee, EmployeeStatusLog,
    MoneyReceipt, Voucher, SalarySheet, AdmissionApplication,
    PromotionBatch, StudentPromotionHistory, AuditLog,
)


DEPARTMENT_PERMISSIONS = {
    "Admission": [
        (AdmissionApplication, ["add", "change", "view"]),
        (Student, ["add", "change", "delete"]),
        (TransferCertificate, ["add", "change", "delete"]),
        (Certificate, ["add", "change", "delete"]),
        (PromotionBatch, ["add", "change", "view"]),
        (StudentPromotionHistory, ["add", "view"]),
    ],
    "Subjects": [
        (Subject, ["add", "change", "delete"]),
    ],
    "Exam": [
        (SSCRegistration, ["add", "change", "delete"]),
        (BoardResult, ["add", "change", "delete"]),
        (Exam, ["add", "change", "delete"]),
        (ExamMark, ["add", "change", "delete"]),
        (SeatPlan, ["add", "change", "delete"]),
    ],
    "HR": [
        (Employee, ["add", "change", "delete"]),
        (EmployeeStatusLog, ["add", "view"]),
    ],
    "Accounts": [
        (AdmissionApplication, ["change", "view"]),
        (MoneyReceipt, ["add", "change", "delete"]),
        (Voucher, ["add", "change", "delete"]),
        (SalarySheet, ["add", "change", "delete"]),
        (Exam, ["add", "change", "delete"]),
        (ExamMark, ["add", "change", "delete"]),
    ],
    "Audit": [
        (AuditLog, ["view"]),
    ],
}


class Command(BaseCommand):
    help = "Create/update department groups and report permission changes."

    def handle(self, *args, **options):
        for group_name, model_permissions in DEPARTMENT_PERMISSIONS.items():
            group, created = Group.objects.get_or_create(name=group_name)
            before = set(group.permissions.values_list('codename', flat=True))
            before_count = len(before)
            group.permissions.clear()

            for model, actions in model_permissions:
                content_type = ContentType.objects.get_for_model(model)
                model_name = model._meta.model_name
                for action in actions:
                    codename = f"{action}_{model_name}"
                    permission = Permission.objects.get(
                        content_type=content_type, codename=codename
                    )
                    group.permissions.add(permission)

            after = set(group.permissions.values_list('codename', flat=True))
            status = "Created new" if created else "Found existing"
            self.stdout.write(self.style.SUCCESS(
                f"{status} group '{group_name}': {before_count} -> {len(after)} permission(s)."
            ))
            removed = before - after
            added = after - before
            if removed:
                self.stdout.write(f"  Removed: {', '.join(sorted(removed))}")
            if added:
                self.stdout.write(f"  Added:   {', '.join(sorted(added))}")

        self.stdout.write(self.style.SUCCESS("Department groups setup complete."))