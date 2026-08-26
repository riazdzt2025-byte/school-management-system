"""
python manage.py setup_groups

Django Groups + Permissions তৈরি করে ডিপার্টমেন্ট-ওয়াইজ এক্সেসের জন্য।
প্রতিটা group নিজের মডেলে add/change/delete পায়, বাকি সব মডেলে শুধু view পায়।
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType

# app_label সবসময় "students" — models.py এই app-এর ভেতরেই আছে
DEPARTMENT_MODELS = {
    "Admission": [("students", "student"), ("students", "certificate")],
    "Exam":      [("students", "subject"), ("students", "studentsubject")],
}

# সব মডেলের ফ্ল্যাট লিস্ট (view পারমিশন সবাইকে দেওয়ার জন্য)
ALL_MODELS = [
    ("students", "student"),
    ("students", "certificate"),
    ("students", "subject"),
    ("students", "studentsubject"),
]

ACTIONS_FULL = ["add", "change", "delete", "view"]


class Command(BaseCommand):
    help = "Create department groups with module-wise permissions"

    def handle(self, *args, **options):
        for dept_name, own_models in DEPARTMENT_MODELS.items():
            group, created = Group.objects.get_or_create(name=dept_name)
            group.permissions.clear()

            for app_label, model_name in ALL_MODELS:
                try:
                    ct = ContentType.objects.get(app_label=app_label, model=model_name)
                except ContentType.DoesNotExist:
                    self.stdout.write(self.style.WARNING(
                        f"  ContentType পাওয়া যায়নি: {app_label}.{model_name}"
                    ))
                    continue

                is_own = (app_label, model_name) in own_models
                actions = ACTIONS_FULL if is_own else ["view"]

                for action in actions:
                    codename = f"{action}_{model_name}"
                    try:
                        perm = Permission.objects.get(content_type=ct, codename=codename)
                        group.permissions.add(perm)
                    except Permission.DoesNotExist:
                        self.stdout.write(self.style.WARNING(
                            f"  Permission পাওয়া যায়নি: {codename}"
                        ))

            self.stdout.write(self.style.SUCCESS(f"✔ Group তৈরি/আপডেট হয়েছে: {dept_name}"))

        self.stdout.write(self.style.SUCCESS("সব Department Group সেটআপ সম্পন্ন হয়েছে।"))