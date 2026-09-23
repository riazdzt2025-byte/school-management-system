"""EX-06 · final-GPA rounding and 4.90–4.99 benefit regression tests.

The D-GPA policy applies *after* deterministic two-place decimal rounding:
passing results whose rounded GPA is in [4.90, 5.00) display as 5.00 / A+.
Fail and No Marks take their own paths and never reach that benefit.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from .models import Exam, ExamMark, Institution, Student, Subject, SubjectRequirement
from .result_utils import build_exam_results, calculate_passing_gpa


def _result_for(results, student):
    return next(row for row in results if row['student'].pk == student.pk)


class GPABoostRoundingTests(SimpleTestCase):
    """Pin every D-GPA boundary to ROUND_HALF_UP, not Decimal's context default."""

    def test_rounding_boundaries_and_cap_are_deterministic(self):
        # The requested policy boundaries plus 4.885, which differs from the
        # default ROUND_HALF_EVEN behaviour and proves the explicit mode matters.
        cases = (
            ('4.894', '4.89', False),
            ('4.895', '5.00', True),
            ('4.899', '5.00', True),
            ('4.90', '5.00', True),
            ('4.949', '5.00', True),
            ('4.99', '5.00', True),
            ('4.999', '5.00', False),
            ('5.00', '5.00', False),
            ('4.885', '4.89', False),
            ('5.005', '5.00', False),
        )
        for raw, expected_gpa, expected_boost in cases:
            with self.subTest(raw=raw):
                gpa, was_boosted = calculate_passing_gpa(Decimal(raw))
                self.assertEqual(gpa, Decimal(expected_gpa))
                self.assertEqual(was_boosted, expected_boost)


class GPABoostResultSurfaceTests(TestCase):
    """One cohort proves boost, rank, fail/AB guard, and every result surface."""

    @classmethod
    def setUpTestData(cls):
        cls.institution = Institution.objects.create(name='EX06 GPA School', classes='9')
        cls.user = get_user_model().objects.create_superuser(
            username='ex06-admin', password='password',
        )
        cls.exam = Exam.objects.create(
            name='Final GPA Examination-2026', exam_type='SECOND_TERM',
            institution=cls.institution, admission_class='9', session='2026', is_published=True,
        )
        # Multi-term analysis deliberately needs two published exams.  This
        # comparison exam has no marks; the selected EX-06 exam remains the
        # first result in each student's row and is what this test asserts.
        cls.comparison_exam = Exam.objects.create(
            name='First Term Comparison-2026', exam_type='FIRST_TERM',
            institution=cls.institution, admission_class='9', session='2026', is_published=True,
        )
        cls.perfect = Student.objects.create(
            institution=cls.institution, student_id='EX06001', name='Perfect Five',
            admission_class='9', section='A', roll_no=1, admission_year=2026,
        )
        cls.boosted = Student.objects.create(
            institution=cls.institution, student_id='EX06002', name='Boosted Four Ninety Five',
            admission_class='9', section='A', roll_no=2, admission_year=2026,
        )
        cls.no_boost = Student.objects.create(
            institution=cls.institution, student_id='EX06003', name='Unboosted Four Eighty Nine',
            admission_class='9', section='A', roll_no=3, admission_year=2026,
        )
        cls.absent = Student.objects.create(
            institution=cls.institution, student_id='EX06004', name='Absent Must Not Boost',
            admission_class='9', section='A', roll_no=4, admission_year=2026,
        )
        cls.failed = Student.objects.create(
            institution=cls.institution, student_id='EX06005', name='Failed Must Not Boost',
            admission_class='9', section='A', roll_no=5, admission_year=2026,
        )

        Subject.objects.bulk_create([
            Subject(code=f'X6{index:03}', name=f'EX06 Subject {index:03}', full_marks=100)
            for index in range(100)
        ])
        cls.subjects = list(Subject.objects.filter(code__startswith='X6').order_by('code'))
        SubjectRequirement.objects.bulk_create([
            SubjectRequirement(
                institution=cls.institution, admission_class='9', group='',
                subject=subject, requirement_type='MANDATORY',
            )
            for subject in cls.subjects
        ])

        marks = []
        for index, subject in enumerate(cls.subjects):
            # Raw GPA: 100 × 5.00 / 100 = 5.00.
            marks.append(ExamMark(
                exam=cls.exam, student=cls.perfect, subject=subject, marks_obtained=80,
            ))
            # 95 × 5.00 + 5 × 4.00 = 4.95 -> 5.00/A+ after the benefit.
            marks.append(ExamMark(
                exam=cls.exam, student=cls.boosted, subject=subject,
                marks_obtained=80 if index < 95 else 70,
            ))
            # 89 × 5.00 + 11 × 4.00 = 4.89: it must not be lifted.
            marks.append(ExamMark(
                exam=cls.exam, student=cls.no_boost, subject=subject,
                marks_obtained=80 if index < 89 else 70,
            ))
            # A blank final paper is AB/F under the default policy and blocks
            # any benefit, even though the other 99 papers are A+.
            if index < 99:
                marks.append(ExamMark(
                    exam=cls.exam, student=cls.absent, subject=subject, marks_obtained=80,
                ))
            # A real F likewise blocks the benefit.
            marks.append(ExamMark(
                exam=cls.exam, student=cls.failed, subject=subject,
                marks_obtained=80 if index < 99 else 30,
            ))
        ExamMark.objects.bulk_create(marks)

    def setUp(self):
        self.client.force_login(self.user)

    def test_boost_boundary_fail_and_absent_cases_keep_correct_positions(self):
        _columns, results = build_exam_results(self.exam)
        perfect = _result_for(results, self.perfect)
        boosted = _result_for(results, self.boosted)
        no_boost = _result_for(results, self.no_boost)
        absent = _result_for(results, self.absent)
        failed = _result_for(results, self.failed)

        self.assertEqual((perfect['gpa'], perfect['position']), (Decimal('5.00'), 1))
        # Position is calculated after the boosted GPA.  The unboosted 5.00
        # retains first place on its larger total, and 4.89 remains third.
        self.assertEqual((boosted['gpa'], boosted['grade'], boosted['position']), (
            Decimal('5.00'), 'A+', 2,
        ))
        self.assertEqual((no_boost['gpa'], no_boost['grade'], no_boost['position']), (
            Decimal('4.89'), 'A', 3,
        ))
        for row in (absent, failed):
            self.assertEqual((row['status'], row['gpa'], row['grade'], row['position']), (
                'Fail', Decimal('0.00'), 'F', None,
            ))
        absent_subject = next(item for item in absent['subject_results'] if item['absent'])
        self.assertEqual((absent_subject['grade'], absent_subject['obtained']), ('F', Decimal('0')))

    def test_every_existing_result_view_and_print_surface_uses_the_boosted_gpa(self):
        """There is no GPA result-export endpoint; browser-print pages are included."""
        _columns, calculated = build_exam_results(self.exam)
        expected = _result_for(calculated, self.boosted)
        self.assertEqual((expected['gpa'], expected['grade'], expected['position']), (
            Decimal('5.00'), 'A+', 2,
        ))

        def assert_boosted(row):
            self.assertEqual((row['gpa'], row['grade'], row['position']), (
                Decimal('5.00'), 'A+', 2,
            ))

        # Register and ranking outputs.
        response = self.client.get(reverse('result_sheet', args=[self.exam.pk]))
        assert_boosted(_result_for(response.context['results'], self.boosted))
        response = self.client.get(reverse('exam_result_summary', args=[self.exam.pk]))
        assert_boosted(_result_for(response.context['results'], self.boosted))
        response = self.client.get(reverse('full_rank_list', args=[self.exam.pk]))
        assert_boosted(_result_for(response.context['results'], self.boosted))
        response = self.client.get(reverse('top_10', args=[self.exam.pk]))
        assert_boosted(_result_for(response.context['results'], self.boosted))

        # Per-student detail and the printable result card.
        response = self.client.get(
            reverse('student_result_detail', args=[self.exam.pk, self.boosted.pk])
        )
        assert_boosted(response.context['result'])
        self.assertContains(response, '5.00')
        response = self.client.get(reverse('result_card', args=[self.exam.pk, self.boosted.pk]))
        assert_boosted(response.context['result'])
        self.assertContains(response, 'GPA: 5.00')

        # Result Analysis pages share build_exam_results as well.
        response = self.client.get(reverse('result_analysis_result_cards'), {'exam': self.exam.pk})
        assert_boosted(_result_for(response.context['results'], self.boosted))
        response = self.client.get(
            reverse('result_analysis_multi_term'),
            {'exams': [self.exam.pk, self.comparison_exam.pk]},
        )
        multi_term_row = next(row for row in response.context['rows'] if row['student'].pk == self.boosted.pk)
        assert_boosted(multi_term_row['results'][0])
        response = self.client.get(reverse('result_analysis_merit_slides'), {'exam': self.exam.pk})
        assert_boosted(_result_for(response.context['top_three'], self.boosted))

        # Subject-fail analysis has no overall-GPA field; it still gets the same
        # AB/F source for the absent student and must not regrade the cohort.
        response = self.client.get(reverse('result_analysis_subject_fail'), {'exam': self.exam.pk})
        last_subject_fails = next(
            bucket for bucket in response.context['subjects_with_fails']
            if bucket['subject'].pk == self.subjects[-1].pk
        )
        absent_row = next(row for row in last_subject_fails['rows'] if row['student'].pk == self.absent.pk)
        self.assertEqual((absent_row['absent'], absent_row['grade']), (True, 'F'))
