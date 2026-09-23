"""EX-05 · Missing marks → Absent/Fail — one rule, one token, everywhere.

D-MIS (owner decision 2026-09-17): a blank assigned subject is **Absent** —
the cell token is ``AB`` on every surface that prints subject cells, the
subject is graded **F** and counted as 0 out of its Full Marks
(``EXAM_ABSENT_SUBJECT_FAILS=True``, the default), an all-blank student is
``No Marks`` (never ranked), and TC/DISCONTINUED students are not in the
register at all. These tests pin that every result view shows the *same*
GPA/status for the same exam (they all read ``build_exam_results`` — nobody
recomputes), that the absent token is the same everywhere, that a real
entered 0 is a different thing from a blank, and that the
``EXAM_ABSENT_SUBJECT_FAILS=False`` path renders truthfully too.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Exam, ExamMark, Institution, Student, Subject, SubjectRequirement
from .result_utils import build_exam_results, get_exam_students


def _row(results, student):
    return next(row for row in results if row['student'].pk == student.pk)


class AbsentTokenConsistencyTests(TestCase):
    """One exam, one partially-entered student — every surface must agree."""

    def setUp(self):
        self.institution = Institution.objects.create(name='EX05 Consistency School', classes='9')
        self.user = get_user_model().objects.create_superuser(username='ex05-admin', password='password')
        self.client.force_login(self.user)
        self.physics = Subject.objects.create(code='PHY5', name='Physics', full_marks=100)
        self.math = Subject.objects.create(code='MTH5', name='Mathematics', full_marks=100)
        for subject in (self.physics, self.math):
            # Group-neutral so both are columns for every student of the class.
            SubjectRequirement.objects.create(
                institution=self.institution, admission_class='9', group='',
                subject=subject, requirement_type='MANDATORY',
            )
        self.exam = Exam.objects.create(
            name='Second Term Examination-2026', exam_type='SECOND_TERM',
            institution=self.institution, admission_class='9', session='2026', is_published=True,
        )
        # A second published exam so the multi-term comparison has two to pick.
        self.other_exam = Exam.objects.create(
            name='First Term Examination-2026', exam_type='FIRST_TERM',
            institution=self.institution, admission_class='9', session='2026', is_published=True,
        )
        self.partial = Student.objects.create(
            institution=self.institution, student_id='X501', name='Half Present',
            admission_class='9', section='A', roll_no=1, admission_year=2026,
        )
        self.sitter = Student.objects.create(
            institution=self.institution, student_id='X502', name='Both Papers',
            admission_class='9', section='A', roll_no=2, admission_year=2026,
        )
        self.zero = Student.objects.create(
            institution=self.institution, student_id='X503', name='Real Zero',
            admission_class='9', section='A', roll_no=3, admission_year=2026,
        )
        ExamMark.objects.create(exam=self.exam, student=self.partial, subject=self.physics, marks_obtained=95)
        ExamMark.objects.create(exam=self.exam, student=self.sitter, subject=self.physics, marks_obtained=80)
        ExamMark.objects.create(exam=self.exam, student=self.sitter, subject=self.math, marks_obtained=64)
        # A *real* entered 0 in Physics — counted, failed, and printed as 0.
        ExamMark.objects.create(exam=self.exam, student=self.zero, subject=self.physics, marks_obtained=0)
        ExamMark.objects.create(exam=self.exam, student=self.zero, subject=self.math, marks_obtained=70)
        ExamMark.objects.create(exam=self.other_exam, student=self.partial, subject=self.physics, marks_obtained=90)

    # ---- the rule itself, as computed by the one and only source ----

    def test_partially_entered_student_fails_on_the_missing_subject(self):
        _, results = build_exam_results(self.exam)
        row = _row(results, self.partial)
        self.assertEqual(row['status'], 'Fail')
        self.assertEqual(str(row['gpa']), '0.00')
        self.assertEqual(row['total_obtained'], 95)   # the absent paper counts 0/100
        self.assertEqual(row['total_full'], 200)
        self.assertIsNone(row['position'])
        absent = [r for r in row['subject_results'] if r['absent'] and not r.get('not_applicable')]
        self.assertEqual(len(absent), 1)
        self.assertEqual(absent[0]['grade'], 'F')
        self.assertEqual(absent[0]['obtained'], 0)

    # ---- every view shows the same GPA/status for the same exam ----

    def test_every_result_view_agrees_on_gpa_and_status(self):
        _, results = build_exam_results(self.exam)
        partial_row, sitter_row = _row(results, self.partial), _row(results, self.sitter)
        surfaces = 0

        # Register (roll order) and the three ranking outputs.
        response = self.client.get(reverse('result_sheet', args=[self.exam.pk]))
        self.assertEqual(_row(response.context['results'], self.partial)['status'], partial_row['status'])
        self.assertEqual(_row(response.context['results'], self.partial)['gpa'], partial_row['gpa'])
        surfaces += 1
        response = self.client.get(reverse('exam_result_summary', args=[self.exam.pk]))
        self.assertEqual(_row(response.context['results'], self.partial)['status'], 'Fail')
        self.assertEqual(_row(response.context['results'], self.sitter)['gpa'], sitter_row['gpa'])
        surfaces += 1
        response = self.client.get(reverse('full_rank_list', args=[self.exam.pk]))
        unranked = _row(response.context['unranked_results'], self.partial)
        self.assertEqual(unranked['status'], 'Fail')
        self.assertEqual(unranked['gpa'], partial_row['gpa'])
        surfaces += 1
        response = self.client.get(reverse('top_10', args=[self.exam.pk]))
        # Only passing students are ranked; the Fail row is not on this page.
        self.assertNotIn(self.partial.pk, [r['student'].pk for r in response.context['results']])
        self.assertEqual(_row(response.context['results'], self.sitter)['gpa'], sitter_row['gpa'])
        surfaces += 1

        # Per-student surfaces.
        response = self.client.get(reverse('student_result_detail', args=[self.exam.pk, self.partial.pk]))
        self.assertEqual(response.context['result']['status'], partial_row['status'])
        self.assertEqual(response.context['result']['gpa'], partial_row['gpa'])
        surfaces += 1
        response = self.client.get(reverse('result_card', args=[self.exam.pk, self.partial.pk]))
        self.assertEqual(response.context['result']['status'], partial_row['status'])
        self.assertEqual(response.context['result']['gpa'], partial_row['gpa'])
        surfaces += 1

        # Result Analysis surfaces (same department gate, same source).
        response = self.client.get(reverse('result_analysis_subject_fail'), {'exam': self.exam.pk})
        math_bucket = next(
            b for b in response.context['subjects_with_fails'] if b['subject'].pk == self.math.pk
        )
        partial_fail = next(r for r in math_bucket['rows'] if r['student'].pk == self.partial.pk)
        self.assertTrue(partial_fail['absent'])
        self.assertEqual(partial_fail['grade'], 'F')
        surfaces += 1
        response = self.client.get(reverse('result_analysis_result_cards'), {'exam': self.exam.pk})
        self.assertEqual(_row(response.context['results'], self.partial)['gpa'], partial_row['gpa'])
        surfaces += 1
        response = self.client.get(
            reverse('result_analysis_multi_term'), {'exams': [self.exam.pk, self.other_exam.pk]},
        )
        row = next(r for r in response.context['rows'] if r['student'].pk == self.partial.pk)
        this_exam = next(
            result for result in row['results']
            if result is not None and result['status'] == 'Fail'
        )
        self.assertEqual(this_exam['status'], partial_row['status'])
        self.assertEqual(this_exam['gpa'], partial_row['gpa'])
        surfaces += 1
        response = self.client.get(reverse('result_analysis_merit_slides'), {'exam': self.exam.pk})
        self.assertNotIn(self.partial.pk, [r['student'].pk for r in response.context['top_three']])
        self.assertEqual(_row(response.context['top_three'], self.sitter)['gpa'], sitter_row['gpa'])
        surfaces += 1

        # 10 verified surfaces: register, summary, rank list, top 10, detail,
        # card, subject-fail, class cards, multi-term, merit slides.
        self.assertEqual(surfaces, 10)

    # ---- the absent token is AB everywhere a cell is printed ----

    def test_AB_token_is_the_same_on_every_surface_that_prints_cells(self):
        register = self.client.get(reverse('result_sheet', args=[self.exam.pk])).content.decode()
        self.assertIn('<span class="mark-number">AB</span>', register)
        self.assertIn('no mark entered - counted as F', register)  # tooltip, default policy
        detail = self.client.get(
            reverse('student_result_detail', args=[self.exam.pk, self.partial.pk])
        ).content.decode()
        self.assertIn('<strong>AB</strong>', detail)
        card = self.client.get(
            reverse('result_card', args=[self.exam.pk, self.partial.pk])
        ).content.decode()
        self.assertIn('AB<br><small>Absent</small>', card)
        self.assertNotIn('<small>absent</small>', card)  # the old en-dash token is gone
        class_cards = self.client.get(
            reverse('result_analysis_result_cards'), {'exam': self.exam.pk}
        ).content.decode()
        self.assertIn('<td>AB</td>', class_cards)
        self.assertNotIn('>Absent<', class_cards)  # the old word token is gone
        subject_fail = self.client.get(
            reverse('result_analysis_subject_fail'), {'exam': self.exam.pk}
        ).content.decode()
        self.assertIn('<td>AB</td>', subject_fail)
        self.assertNotIn('>Absent<', subject_fail)

    # ---- an entered 0 is not an absent ----

    def test_entered_zero_is_counted_and_printed_as_zero_not_AB(self):
        _, results = build_exam_results(self.exam)
        row = _row(results, self.zero)
        physics = next(
            r for r in row['subject_results'] if r['subject'].pk == self.physics.pk
        )
        self.assertFalse(physics['absent'])
        self.assertEqual(physics['obtained'], 0)
        self.assertEqual(physics['grade'], 'F')
        self.assertEqual(row['total_obtained'], 70)  # 0 + 70: the 0 is counted
        self.assertEqual(row['status'], 'Fail')
        # The register prints a real 0 in the cell — AB is only for blanks.
        content = self.client.get(reverse('result_sheet', args=[self.exam.pk])).content.decode()
        self.assertIn('<span class="mark-number">0</span>', content)
        # And the subject-fail analysis shows 0/100, not AB, for this student.
        subject_fail = self.client.get(
            reverse('result_analysis_subject_fail'), {'exam': self.exam.pk}
        ).content.decode()
        self.assertIn('<td>0/100</td>', subject_fail)

    # ---- EXAM_ABSENT_SUBJECT_FAILS=False renders truthfully too ----

    @override_settings(EXAM_ABSENT_SUBJECT_FAILS=False)
    def test_absent_rule_off_excludes_the_subject_and_prints_AB_without_F(self):
        _, results = build_exam_results(self.exam)
        row = _row(results, self.partial)
        self.assertEqual(row['status'], 'Pass')       # only the sat paper counts
        self.assertEqual(row['total_full'], 100)
        self.assertEqual(str(row['gpa']), '5.00')
        absent = [r for r in row['subject_results'] if r['absent'] and not r.get('not_applicable')]
        self.assertEqual(absent[0]['grade'], '-')
        self.assertIsNone(absent[0]['obtained'])

        register = self.client.get(reverse('result_sheet', args=[self.exam.pk])).content.decode()
        self.assertIn('<span class="mark-number">AB</span>', register)   # token unchanged
        self.assertNotIn('counted as F', register)                       # ...but it is not an F here
        self.assertNotIn('counted as 0 out of its Full Marks', register)
        self.assertIn('not counted (EXAM_ABSENT_SUBJECT_FAILS off)', register)
        self.assertIn('<span class="grade-badge grade-muted">-</span>', register)

        detail = self.client.get(
            reverse('student_result_detail', args=[self.exam.pk, self.partial.pk])
        ).content.decode()
        self.assertIn('left out of the total and the GPA', detail)
        summary = self.client.get(reverse('exam_result_summary', args=[self.exam.pk]))
        self.assertEqual(_row(summary.context['results'], self.partial)['status'], 'Pass')

    # ---- TC / DISCONTINUED never reach the register ----

    def test_tc_and_discontinued_students_are_not_in_the_register(self):
        transferred = Student.objects.create(
            institution=self.institution, student_id='X5T', name='TC Kid',
            admission_class='9', section='A', roll_no=8, admission_year=2026, status='TRANSFERRED',
        )
        discontinued = Student.objects.create(
            institution=self.institution, student_id='X5D', name='Disc Kid',
            admission_class='9', section='A', roll_no=9, admission_year=2026, status='DISCONTINUED',
        )
        for student in (transferred, discontinued):
            ExamMark.objects.create(
                exam=self.exam, student=student, subject=self.physics, marks_obtained=50,
            )
        students = list(get_exam_students(self.exam))
        self.assertNotIn(transferred.pk, [s.pk for s in students])
        self.assertNotIn(discontinued.pk, [s.pk for s in students])
        response = self.client.get(reverse('result_sheet', args=[self.exam.pk]))
        register_pks = [row['student'].pk for row in response.context['results']]
        self.assertNotIn(transferred.pk, register_pks)
        self.assertNotIn(discontinued.pk, register_pks)
        self.assertEqual(len(register_pks), 3)
