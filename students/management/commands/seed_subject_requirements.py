from django.core.management.base import BaseCommand, CommandError
from students.models import Institution, Subject, SubjectRequirement


# Standard Bangladesh SSC (class 9-10) group-wise subject structure under the
# NCTB curriculum. This is a reference starting point, not a legal document —
# institutions can add, edit, or delete individual rows afterwards from the
# "Subject Requirements" page, since exact syllabi can vary slightly by board
# / institution and do change over time.
#
# Each entry: (subject_code, requirement_type, optional_set_key, condition_religion)
# These are applied with group='' (i.e. common/compulsory across every group).
COMMON_REQUIREMENTS = [
    ('BAN1', 'MANDATORY', '', ''),
    ('BAN2', 'MANDATORY', '', ''),
    ('ENG1', 'MANDATORY', '', ''),
    ('ENG2', 'MANDATORY', '', ''),
    ('ICT', 'MANDATORY', '', ''),
    ('BGS', 'MANDATORY', '', ''),
    ('CAREER', 'MANDATORY', '', ''),
    ('HPE', 'MANDATORY', '', ''),
    ('ART', 'MANDATORY', '', ''),
    ('ISLAM', 'CONDITIONAL', '', 'Islam'),
    ('HINDU', 'CONDITIONAL', '', 'Hindu'),
    ('CHRIS', 'CONDITIONAL', '', 'Christian'),
    ('BUDDHIST', 'CONDITIONAL', '', 'Buddhist'),
]

GROUP_REQUIREMENTS = {
    'SCI': [
        ('MATH', 'MANDATORY', '', ''),
        ('PHY', 'MANDATORY', '', ''),
        ('CHEM', 'MANDATORY', '', ''),
        ('BIO', 'OPTIONAL', 'sci_4th', ''),
        ('HMATH', 'OPTIONAL', 'sci_4th', ''),
    ],
    'BUS': [
        ('MATH', 'MANDATORY', '', ''),
        ('ACC', 'MANDATORY', '', ''),
        ('BOM', 'MANDATORY', '', ''),
        ('FIN', 'OPTIONAL', 'bus_4th', ''),
        ('ECO', 'OPTIONAL', 'bus_4th', ''),
    ],
    'HUM': [
        ('SCI-GEN', 'MANDATORY', '', ''),
        ('CIVICS', 'OPTIONAL', 'hum_elective_1', ''),
        ('HISTORY', 'OPTIONAL', 'hum_elective_1', ''),
        ('GEO', 'OPTIONAL', 'hum_elective_1', ''),
        ('ECO', 'OPTIONAL', 'hum_elective_1', ''),
        ('LOGIC', 'OPTIONAL', 'hum_elective_2', ''),
        ('SOC', 'OPTIONAL', 'hum_elective_2', ''),
        ('PSY', 'OPTIONAL', 'hum_elective_2', ''),
        ('MATH', 'OPTIONAL', 'hum_elective_2', ''),
    ],
}

SSC_CLASSES = ['9', '10']


class Command(BaseCommand):
    help = (
        "Auto-populate standard SSC (class 9-10) SubjectRequirement rows — "
        "compulsory subjects plus Science/Business Studies/Humanities group "
        "subjects — for one institution or all institutions. Existing rows "
        "are left untouched (safe to re-run)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--institution', type=int, default=None,
            help='Institution ID to seed. If omitted, seeds every institution that has class 9 or 10.',
        )

    def handle(self, *args, **options):
        institution_id = options['institution']
        if institution_id:
            institutions = Institution.objects.filter(pk=institution_id)
            if not institutions.exists():
                raise CommandError(f"No institution with id={institution_id}")
        else:
            institutions = Institution.objects.all()

        missing_codes = set()
        created_total = 0
        skipped_total = 0
        touched_institutions = 0

        for institution in institutions:
            classes_here = [c for c in institution.get_class_list() if c in SSC_CLASSES]
            if not classes_here:
                continue
            touched_institutions += 1

            for admission_class in classes_here:
                created_total += self._apply_rows(
                    institution, admission_class, group='', rows=COMMON_REQUIREMENTS,
                    missing_codes=missing_codes,
                )
                for group_code, rows in GROUP_REQUIREMENTS.items():
                    created_total += self._apply_rows(
                        institution, admission_class, group=group_code, rows=rows,
                        missing_codes=missing_codes,
                    )

        if missing_codes:
            self.stdout.write(self.style.WARNING(
                "Some subject codes referenced here don't exist in the Subject master list "
                "(run 'python manage.py seed_subjects' first): " + ', '.join(sorted(missing_codes))
            ))

        self.stdout.write(self.style.SUCCESS(
            f"Done — {touched_institutions} institution(s) processed, "
            f"{created_total} SubjectRequirement row(s) created (existing rows were left as-is)."
        ))

    def _apply_rows(self, institution, admission_class, group, rows, missing_codes):
        created = 0
        for code, req_type, opt_key, condition_religion in rows:
            try:
                subject = Subject.objects.get(code=code)
            except Subject.DoesNotExist:
                missing_codes.add(code)
                continue
            _, was_created = SubjectRequirement.objects.get_or_create(
                institution=institution,
                admission_class=admission_class,
                group=group,
                subject=subject,
                defaults={
                    'requirement_type': req_type,
                    'optional_set_key': opt_key,
                    'condition_religion': condition_religion,
                },
            )
            if was_created:
                created += 1
        return created
