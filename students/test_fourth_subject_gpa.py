"""Fourth-subject GPA policy regression tests.

A selected ``FOURTH``-category subject contributes only its points above 2.00.
It never makes the main result Fail, is never an eleventh GPA denominator, and
cannot make the published GPA exceed 5.00.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from .models import Exam, ExamMark, Institution, Student, StudentSubjectChoice, Subject, SubjectRequirement
from .result_utils import (
    build_exam_results,
    calculate_final_gpa,
    fourth_subject_configuration_errors,
)


def _result_for(results, student):
    return next(row for row in results if row['student'].pk == student.pk)


class FourthSubjectGPAFormulaTests(SimpleTestCase):
    def test_bonus_uses_main_subject_count_and_caps_at_five(self):
        # 10 main papers at 4.80 plus an A+ fourth paper:
        # (48 + max(0, 5 - 2)) / 10 = 5.10 -> 5.00, never 5.10/5.20.
        self.assertEqual(
            calculate_final_gpa([Decimal('5.00')] * 8 + [Decimal('4.00')] * 2, Decimal('5.00')),
            Decimal('5.00'),
        )

    def test_fourth_failure_gives_zero_bonus_and_old_boost_is_gone(self):
        main_points = [Decimal('5.00')] * 9 + [Decimal('4.00')]
        # No fourth subject: raw 4.90 stays 4.90. The former 4.90 -> 5.00
        # benefit was explicitly replaced by the owner-confirmed fourth rule.
        self.assertEqual(calculate_final_gpa(main_points), Decimal('4.90'))
        # F = 0 points, so it earns no bonus and cannot cause a failure itself.
        self.assertEqual(calculate_final_gpa(main_points, Decimal('0.00')), Decimal('4.90'))


class FourthSubjectResultTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.institution = Institution.objects.create(name='Fourth Subject School', classes='9')
        cls.user = get_user_model().objects.create_superuser(
            username='fourth-subject-admin', password='password',
        )
        cls.exam = Exam.objects.create(
            name='Fourth Subject Examination-2026', exam_type='SECOND_TERM',
            institution=cls.institution, admission_class='9', session='2026', is_published=True,
        )
        cls.comparison_exam = Exam.objects.create(
            name='First Term Comparison-2026', exam_type='FIRST_TERM',
            institution=cls.institution, admission_class='9', session='2026', is_published=True,
        )
        cls.main_subjects = [
            Subject.objects.create(code=f'F4M{index}', name=f'Main Subject {index}', full_marks=100)
            for index in range(10)
        ]
        cls.agriculture = Subject.objects.create(
            code='AGRI4T', name='Agriculture Studies (4th Subject)',
            full_marks=100, category='FOURTH',
        )
        cls.statistics = Subject.objects.create(
            code='STAT4T', name='Statistics (4th Subject)',
            full_marks=100, category='FOURTH',
        )
        cls.elective = Subject.objects.create(
            code='ELECT4T', name='Ordinary Optional Elective',
            full_marks=100, category='OTHER',
        )
        cls.main_requirements = [
            SubjectRequirement.objects.create(
                institution=cls.institution, admission_class='9', subject=subject,
                requirement_type='MANDATORY',
            )
            for subject in cls.main_subjects
        ]
        cls.agriculture_requirement = SubjectRequirement.objects.create(
            institution=cls.institution, admission_class='9', subject=cls.agriculture,
            requirement_type='OPTIONAL', optional_set_key='fourth-choice',
        )
        cls.statistics_requirement = SubjectRequirement.objects.create(
            institution=cls.institution, admission_class='9', subject=cls.statistics,
            requirement_type='OPTIONAL', optional_set_key='fourth-choice',
        )
        cls.elective_requirement = SubjectRequirement.objects.create(
            institution=cls.institution, admission_class='9', subject=cls.elective,
            requirement_type='OPTIONAL', optional_set_key='ordinary-elective',
        )
        cls.capped = Student.objects.create(
            institution=cls.institution, student_id='F4001', name='Bonus Caps At Five',
            admission_class='9', section='A', roll_no=1, admission_year=2026,
        )
        cls.fourth_failed = Student.objects.create(
            institution=cls.institution, student_id='F4002', name='Fourth Failure Is Not Main Failure',
            admission_class='9', section='A', roll_no=2, admission_year=2026,
        )
        cls.main_failed = Student.objects.create(
            institution=cls.institution, student_id='F4003', name='Main Failure Still Fails',
            admission_class='9', section='A', roll_no=3, admission_year=2026,
        )
        cls.no_fourth = Student.objects.create(
            institution=cls.institution, student_id='F4004', name='No Fourth Subject',
            admission_class='9', section='A', roll_no=4, admission_year=2026,
        )
        cls.ordinary_optional = Student.objects.create(
            institution=cls.institution, student_id='F4005', name='Ordinary Optional Is Main',
            admission_class='9', section='A', roll_no=5, admission_year=2026,
        )
        for student in (cls.capped, cls.fourth_failed, cls.main_failed, cls.ordinary_optional):
            StudentSubjectChoice.objects.create(student=student, requirement=cls.agriculture_requirement)
        StudentSubjectChoice.objects.create(
            student=cls.ordinary_optional, requirement=cls.elective_requirement,
        )

        marks = []
        for index, subject in enumerate(cls.main_subjects):
            # 8 A+ + 2 A = 48 main points / 10 = 4.80 and 780/1000 marks.
            main_mark = 80 if index < 8 else 70
            marks.extend([
                ExamMark(exam=cls.exam, student=cls.capped, subject=subject, marks_obtained=main_mark),
                ExamMark(exam=cls.exam, student=cls.fourth_failed, subject=subject, marks_obtained=main_mark),
                ExamMark(
                    exam=cls.exam, student=cls.main_failed, subject=subject,
                    marks_obtained=80 if index < 9 else 30,
                ),
                ExamMark(exam=cls.exam, student=cls.no_fourth, subject=subject, marks_obtained=main_mark),
                ExamMark(exam=cls.exam, student=cls.ordinary_optional, subject=subject, marks_obtained=80),
            ])
        marks.extend([
            ExamMark(exam=cls.exam, student=cls.capped, subject=cls.agriculture, marks_obtained=80),
            ExamMark(exam=cls.exam, student=cls.fourth_failed, subject=cls.agriculture, marks_obtained=30),
            ExamMark(exam=cls.exam, student=cls.main_failed, subject=cls.agriculture, marks_obtained=80),
            ExamMark(exam=cls.exam, student=cls.ordinary_optional, subject=cls.agriculture, marks_obtained=80),
            ExamMark(exam=cls.exam, student=cls.ordinary_optional, subject=cls.elective, marks_obtained=70),
        ])
        ExamMark.objects.bulk_create(marks)

    def setUp(self):
        self.client.force_login(self.user)

    def test_fourth_bonus_is_capped_and_fourth_failure_does_not_fail_main_result(self):
        _columns, results = build_exam_results(self.exam)
        capped = _result_for(results, self.capped)
        fourth_failed = _result_for(results, self.fourth_failed)
        main_failed = _result_for(results, self.main_failed)
        no_fourth = _result_for(results, self.no_fourth)

        # The 4th paper is visible but the published total/percentage/GPA
        # denominator remain the ten main papers.
        self.assertEqual((capped['total_obtained'], capped['total_full'], capped['main_subject_count']), (
            Decimal('780'), Decimal('1000'), 10,
        ))
        self.assertEqual((capped['gpa'], capped['grade'], capped['status']), (
            Decimal('5.00'), 'A+', 'Pass',
        ))
        agriculture_row = next(row for row in capped['subject_results'] if row['subject'] == self.agriculture)
        self.assertEqual((agriculture_row['is_fourth_subject'], agriculture_row['counts_toward_result']), (True, False))

        # An F in Agriculture is printed as F, gives no bonus, but does not
        # turn the ten-main-subject result into Fail.
        self.assertEqual((fourth_failed['gpa'], fourth_failed['status']), (Decimal('4.80'), 'Pass'))
        failed_agriculture = next(
            row for row in fourth_failed['subject_results'] if row['subject'] == self.agriculture
        )
        self.assertEqual((failed_agriculture['grade'], failed_agriculture['passed']), ('F', False))
        self.assertEqual((no_fourth['gpa'], no_fourth['status']), (Decimal('4.80'), 'Pass'))

        # A failed main paper still fails the whole result despite an A+ fourth paper.
        self.assertEqual((main_failed['gpa'], main_failed['grade'], main_failed['status']), (
            Decimal('0.00'), 'F', 'Fail',
        ))

        # Requirement type OPTIONAL alone is not enough for fourth-subject
        # treatment: this selected OTHER-category elective is the eleventh
        # *main* paper, while Agriculture remains the one bonus paper.
        ordinary_optional = _result_for(results, self.ordinary_optional)
        elective_row = next(
            row for row in ordinary_optional['subject_results'] if row['subject'] == self.elective
        )
        self.assertEqual((elective_row['is_fourth_subject'], elective_row['counts_toward_result']), (False, True))
        self.assertEqual((ordinary_optional['main_subject_count'], ordinary_optional['total_full']), (11, Decimal('1100')))

    def test_every_result_surface_uses_the_same_capped_fourth_subject_gpa(self):
        _columns, calculated = build_exam_results(self.exam)
        expected = _result_for(calculated, self.capped)

        def assert_capped(row):
            self.assertEqual((row['gpa'], row['grade'], row['status']), (
                Decimal('5.00'), 'A+', 'Pass',
            ))

        for route in ('result_sheet', 'exam_result_summary', 'full_rank_list', 'top_10'):
            response = self.client.get(reverse(route, args=[self.exam.pk]))
            assert_capped(_result_for(response.context['results'], self.capped))
        response = self.client.get(
            reverse('student_result_detail', args=[self.exam.pk, self.capped.pk])
        )
        assert_capped(response.context['result'])
        response = self.client.get(reverse('result_card', args=[self.exam.pk, self.capped.pk]))
        assert_capped(response.context['result'])
        self.assertContains(response, 'GPA: 5.00')

        response = self.client.get(reverse('result_analysis_result_cards'), {'exam': self.exam.pk})
        assert_capped(_result_for(response.context['results'], self.capped))
        response = self.client.get(
            reverse('result_analysis_multi_term'),
            {'exams': [self.exam.pk, self.comparison_exam.pk]},
        )
        multi_term_row = next(row for row in response.context['rows'] if row['student'].pk == self.capped.pk)
        assert_capped(multi_term_row['results'][0])
        response = self.client.get(reverse('result_analysis_merit_slides'), {'exam': self.exam.pk})
        assert_capped(_result_for(response.context['top_three'], self.capped))

    def test_multiple_fourth_subjects_are_a_publish_blocking_configuration_error(self):
        misconfigured = Student.objects.create(
            institution=self.institution, student_id='F4006', name='Two Fourth Subjects',
            admission_class='9', section='A', roll_no=5, admission_year=2026,
        )
        StudentSubjectChoice.objects.bulk_create([
            StudentSubjectChoice(student=misconfigured, requirement=self.agriculture_requirement),
            StudentSubjectChoice(student=misconfigured, requirement=self.statistics_requirement),
        ])
        unpublished = Exam.objects.create(
            name='Unpublished Fourth Configuration-2026', exam_type='FINAL_TERM',
            institution=self.institution, admission_class='9', session='2026', is_published=False,
        )
        errors = fourth_subject_configuration_errors(unpublished)
        self.assertEqual(len(errors), 1)
        self.assertIn('Two Fourth Subjects', errors[0])
        self.assertIn('Agriculture Studies (4th Subject)', errors[0])
        self.assertIn('Statistics (4th Subject)', errors[0])

        response = self.client.post(reverse('toggle_publish_exam', args=[unpublished.pk]), follow=True)
        self.assertContains(response, 'Cannot publish: each student may select at most one fourth subject.')
        unpublished.refresh_from_db()
        self.assertFalse(unpublished.is_published)
