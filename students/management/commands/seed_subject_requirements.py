from django.core.management.base import BaseCommand, CommandError
from students.models import Institution
from students.curriculum_apply import apply_curriculum
from students.curriculum_data import curriculum_for_class


class Command(BaseCommand):
    help = (
        "Auto-populate SubjectRequirement rows from the built-in Bangladesh "
        "curriculum (Primary, Junior Secondary, SSC and HSC, group-wise "
        "where applicable) for one institution or all institutions. "
        "Existing rows are left untouched (safe to re-run). This is the "
        "same logic the 'Auto-fill from Curriculum' button on the Subject "
        "Assignments page uses."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--institution', type=int, default=None,
            help='Institution ID to seed. If omitted, seeds every institution.',
        )

    def handle(self, *args, **options):
        institution_id = options['institution']
        if institution_id:
            institutions = Institution.objects.filter(pk=institution_id)
            if not institutions.exists():
                raise CommandError(f"No institution with id={institution_id}")
        else:
            institutions = Institution.objects.all()

        created_total = 0
        touched_institutions = 0
        skipped_classes = set()

        for institution in institutions:
            classes_here = institution.get_class_list()
            covered_any = False
            for admission_class in classes_here:
                common_rows, _ = curriculum_for_class(admission_class)
                if common_rows is None:
                    skipped_classes.add(admission_class)
                    continue
                covered_any = True
                created_total += apply_curriculum(institution, admission_class)
            if covered_any:
                touched_institutions += 1

        if skipped_classes:
            self.stdout.write(self.style.WARNING(
                "These class labels aren't covered by the built-in curriculum "
                "and were skipped (add their subjects manually): " + ', '.join(sorted(skipped_classes))
            ))

        self.stdout.write(self.style.SUCCESS(
            f"Done — {touched_institutions} institution(s) processed, "
            f"{created_total} SubjectRequirement row(s) created (existing rows were left as-is)."
        ))
