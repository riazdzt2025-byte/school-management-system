"""
Subject display_order ordering tests.

Verifies that the Subject.display_order field controls the serial order
of subjects in result sheets, mark evaluation, and subject lists.
"""

from django.test import TestCase
from django.contrib.auth import get_user_model

from students.models import Institution, Subject, SubjectRequirement


User = get_user_model()


class SubjectDisplayOrderTests(TestCase):
    """Verify subjects appear in display_order, not alphabetical."""

    def setUp(self):
        self.user = User.objects.create_user(username='officer', password='x')
        self.inst = Institution.objects.create(
            name='Test School',
            classes='6,7,8,9,10',
        )

    def _create_subject(self, code, name, display_order=0):
        return Subject.objects.create(
            code=code,
            name=name,
            full_marks=100,
            display_order=display_order,
            created_by=self.user,
        )

    def test_subjects_ordered_by_display_order(self):
        """Subjects with lower display_order appear first."""
        s_math = self._create_subject('MATH', 'Mathematics', display_order=50)
        s_ban1 = self._create_subject('BAN1ST', 'Bangla 1st', display_order=10)
        s_eng1 = self._create_subject('ENG1ST', 'English 1st', display_order=30)

        subjects = list(Subject.objects.all())
        self.assertEqual(subjects[0], s_ban1)
        self.assertEqual(subjects[1], s_eng1)
        self.assertEqual(subjects[2], s_math)

    def test_subject_requirements_ordered_by_display_order(self):
        """SubjectRequirement rows follow subject display_order."""
        s_ict = self._create_subject('ICT', 'ICT', display_order=100)
        s_ban1 = self._create_subject('BAN1ST', 'Bangla 1st', display_order=10)
        s_math = self._create_subject('MATH', 'Mathematics', display_order=50)

        SubjectRequirement.objects.create(
            institution=self.inst,
            admission_class='9',
            subject=s_ict,
            requirement_type='MANDATORY',
        )
        SubjectRequirement.objects.create(
            institution=self.inst,
            admission_class='9',
            subject=s_ban1,
            requirement_type='MANDATORY',
        )
        SubjectRequirement.objects.create(
            institution=self.inst,
            admission_class='9',
            subject=s_math,
            requirement_type='MANDATORY',
        )

        reqs = list(
            SubjectRequirement.objects.filter(
                institution=self.inst,
                admission_class='9',
            )
        )
        self.assertEqual(reqs[0].subject, s_ban1)
        self.assertEqual(reqs[1].subject, s_math)
        self.assertEqual(reqs[2].subject, s_ict)

    def test_get_applicable_subjects_respects_display_order(self):
        """get_applicable_subjects returns subjects in display_order."""
        from students.views import get_applicable_subjects

        s_ban1 = self._create_subject('BAN1ST', 'Bangla 1st', display_order=10)
        s_eng1 = self._create_subject('ENG1ST', 'English 1st', display_order=30)
        s_math = self._create_subject('MATH', 'Mathematics', display_order=50)
        s_agri = self._create_subject('AGRI', 'Agriculture', display_order=60)

        for s in [s_agri, s_math, s_ban1, s_eng1]:
            SubjectRequirement.objects.create(
                institution=self.inst,
                admission_class='9',
                subject=s,
                requirement_type='MANDATORY',
            )

        data = get_applicable_subjects(self.inst, '9')
        mandatory = data['mandatory']
        self.assertEqual(len(mandatory), 4)
        self.assertEqual(mandatory[0]['code'], 'BAN1ST')
        self.assertEqual(mandatory[1]['code'], 'ENG1ST')
        self.assertEqual(mandatory[2]['code'], 'MATH')
        self.assertEqual(mandatory[3]['code'], 'AGRI')

    def test_default_display_order_is_zero(self):
        """New subjects default to display_order=0."""
        s = self._create_subject('TEST', 'Test Subject')
        self.assertEqual(s.display_order, 0)

    def test_nctb_standard_order(self):
        """Verify the standard NCTB subject serial for classes 6-10."""
        from students.views import get_applicable_subjects

        subjects_in_order = [
            ('BAN 1ST', 'Bangla 1st Paper', 10),
            ('BAN 2ND', 'Bangla 2nd Paper', 20),
            ('ENG 1ST', 'English 1st Paper', 30),
            ('ENG 2ND', 'English 2nd Paper', 40),
            ('MATH', 'Mathematics', 50),
            ('AGRI', 'Agriculture', 60),
            ('REL', 'Religion & Moral Education', 70),
            ('SCI', 'Science', 80),
            ('BWO', 'Bangladesh & World', 90),
            ('ICT', 'ICT', 100),
        ]

        for code, name, order in subjects_in_order:
            s = self._create_subject(code, name, display_order=order)
            SubjectRequirement.objects.create(
                institution=self.inst,
                admission_class='9',
                subject=s,
                requirement_type='MANDATORY',
            )

        data = get_applicable_subjects(self.inst, '9')
        mandatory = data['mandatory']
        self.assertEqual(len(mandatory), 10)
        # Verify exact NCTB serial
        expected_codes = [
            'BAN 1ST', 'BAN 2ND', 'ENG 1ST', 'ENG 2ND', 'MATH',
            'AGRI', 'REL', 'SCI', 'BWO', 'ICT',
        ]
        actual_codes = [s['code'] for s in mandatory]
        self.assertEqual(actual_codes, expected_codes)
