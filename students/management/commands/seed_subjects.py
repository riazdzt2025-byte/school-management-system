from django.core.management.base import BaseCommand
from students.models import Subject


# Pre-loaded, commonly-used subjects under the current Bangladesh national
# curriculum (SSC/HSC level). Institutions can still add their own custom
# subjects from the Subjects page if something here doesn't fit.
SUBJECTS = [
    # code, name, full_marks, category
    ('BAN1', 'Bangla 1st Paper', 100, 'COMPULSORY'),
    ('BAN2', 'Bangla 2nd Paper', 100, 'COMPULSORY'),
    ('ENG1', 'English 1st Paper', 100, 'COMPULSORY'),
    ('ENG2', 'English 2nd Paper', 100, 'COMPULSORY'),
    ('MATH', 'General Mathematics', 100, 'COMPULSORY'),
    ('ICT', 'Information & Communication Technology', 50, 'COMPULSORY'),
    ('BGS', 'Bangladesh & Global Studies', 100, 'COMPULSORY'),
    ('SCI-GEN', 'General Science', 100, 'COMPULSORY'),
    ('CAREER', 'Career Education', 50, 'COMPULSORY'),
    ('HPE', 'Health & Physical Education', 50, 'COMPULSORY'),
    ('ART', 'Art & Culture', 50, 'COMPULSORY'),

    ('PHY', 'Physics', 100, 'OPTIONAL'),
    ('CHEM', 'Chemistry', 100, 'OPTIONAL'),
    ('BIO', 'Biology', 100, 'OPTIONAL'),
    ('HMATH', 'Higher Mathematics', 100, 'OPTIONAL'),
    ('AGRI', 'Agriculture Studies', 100, 'OPTIONAL'),
    ('ACC', 'Accounting', 100, 'OPTIONAL'),
    ('BOM', 'Business Organization & Management', 100, 'OPTIONAL'),
    ('FIN', 'Finance, Banking & Insurance', 100, 'OPTIONAL'),
    ('ECO', 'Economics', 100, 'OPTIONAL'),
    ('CIVICS', 'Civics & Good Governance', 100, 'OPTIONAL'),
    ('HISTORY', 'History of Bangladesh & World Civilization', 100, 'OPTIONAL'),
    ('GEO', 'Geography & Environment', 100, 'OPTIONAL'),
    ('LOGIC', 'Logic', 100, 'OPTIONAL'),
    ('SOC', 'Sociology', 100, 'OPTIONAL'),
    ('PSY', 'Psychology', 100, 'OPTIONAL'),

    ('ISLAM', 'Islam & Moral Education', 100, 'RELIGION'),
    ('HINDU', 'Hindu Religion & Moral Education', 100, 'RELIGION'),
    ('CHRIS', 'Christian Religion & Moral Education', 100, 'RELIGION'),
    ('BUDDHIST', 'Buddhist Religion & Moral Education', 100, 'RELIGION'),

    ('DCS', 'Computer & Information Technology (Vocational)', 100, 'VOCATIONAL'),
    ('DEL', 'Electrical Works & Services (Vocational)', 100, 'VOCATIONAL'),
    ('DCV', 'Civil Construction & Maintenance (Vocational)', 100, 'VOCATIONAL'),

    ('ENG3', 'General Science (4th Subject)', 100, 'FOURTH'),
    ('MATH4', 'Higher Mathematics (4th Subject)', 100, 'FOURTH'),
    ('AGRI4', 'Agriculture Studies (4th Subject)', 100, 'FOURTH'),
]


class Command(BaseCommand):
    help = "Load the pre-loaded Bangladesh-curriculum subject list into the Subject master list."

    def handle(self, *args, **options):
        created, skipped = 0, 0
        for code, name, full_marks, category in SUBJECTS:
            _, was_created = Subject.objects.get_or_create(
                code=code,
                defaults={'name': name, 'full_marks': full_marks, 'category': category},
            )
            if was_created:
                created += 1
            else:
                skipped += 1
        self.stdout.write(self.style.SUCCESS(
            f"Seed complete: {created} subject(s) created, {skipped} already existed."
        ))
