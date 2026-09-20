"""Register/roll ordering regression coverage (EX-02, prompt 03/28).

The formal rule this suite pins:

* register/roll-based outputs (student list, Excel export, class attendance
  list, seat plan, signature sheet, class result-card print run, multi-term
  rows, per-subject fail list) sort by **numeric roll** — ``roll_no`` is an
  ``IntegerField``, so rolls 2 / 10 / 100 must never meet the classic
  string-sort trap — with ``name`` then ``pk`` as stable tie-breaks and
  students *without* a roll always last;
* merit/rank outputs (exam result summary, full rank list, top 10, merit
  slides, section arrangement) keep **position order** — intentional.

Rolls 2, 10, 100 and None are exercised everywhere: a string sort would put
10 before 2, a plain ``order_by('roll_no')`` would put the NULL first.
"""
from io import BytesIO

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import (
    Exam, ExamMark, Institution, SeatPlan, Student, Subject, SubjectRequirement,
)
from .result_utils import failed_subject_rows, get_exam_students, section_arrangement_rows


class RegisterRollOrderFixture(TestCase):
    """One published exam, rolls 2/10/100/None plus a duplicate-roll tie pair.

    Merit deliberately inverts the roll order: roll 10 is first in merit,
    roll 2 second … the roll-less student last — so any test that merely
    sees roll order where merit is expected (or vice versa) fails.
    """

    @classmethod
    def setUpTestData(cls):
        cls.institution = Institution.objects.create(name='Roll Order School', classes='6')
        cls.user = get_user_model().objects.create_superuser('roll-admin', 'r@example.com', 'password')
        cls.subject = Subject.objects.create(code='BAN1', name='Bangla 1st Paper', full_marks=100)
        SubjectRequirement.objects.create(
            institution=cls.institution, admission_class='6', subject=cls.subject,
            requirement_type='MANDATORY',
        )
        cls.exam = Exam.objects.create(
            name='Roll Order First Term', exam_type='FIRST_TERM', institution=cls.institution,
            admission_class='6', session='2026', is_published=True,
        )
        cls.exam2 = Exam.objects.create(
            name='Roll Order Second Term', exam_type='SECOND_TERM', institution=cls.institution,
            admission_class='6', session='2026', is_published=True,
        )

        # Created deliberately out of roll order; tieZ gets a lower pk than
        # tieA so the name tie-break (not insertion order) must win.
        def make(student_id, form_no, name, roll, contact):
            return Student.objects.create(
                institution=cls.institution, student_id=student_id, form_no=form_no,
                name=name, admission_class='6', section='A', roll_no=roll,
                guardian_contact_no=contact,
            )

        cls.tie_zed = make('R07Z', '7', 'Zed Tie', 7, '01800000007')      # lower pk, later name
        cls.s_none = make('R000', '0', 'No Roll', None, '01800000000')
        cls.s_10 = make('R010', '10', 'Roll Ten', 10, '01800000010')
        cls.s_2 = make('R002', '2', 'Roll Two', 2, '01800000002')
        cls.tie_abe = make('R07A', '8', 'Abe Tie', 7, '01800000008')      # same roll as Zed
        cls.s_100 = make('R100', '100', 'Roll Hundred', 100, '01800000100')

        # Merit (position) order: 10, 2, 100, Abe(7), Zed(7), None — the
        # exact inverse of the register order.
        marks = {
            cls.s_10.pk: 95, cls.s_2.pk: 90, cls.s_100.pk: 85,
            cls.tie_abe.pk: 80, cls.tie_zed.pk: 75, cls.s_none.pk: 70,
        }
        for exam in (cls.exam, cls.exam2):
            for student in (cls.s_10, cls.s_2, cls.s_100, cls.tie_abe, cls.tie_zed, cls.s_none):
                ExamMark.objects.create(
                    exam=exam, student=student, subject=cls.subject,
                    marks_obtained=marks[student.pk],
                )

    @classmethod
    def register_rolls(cls):
        # The expected register order everywhere: numeric, ties by name, None last.
        return [cls.s_2, cls.tie_abe, cls.tie_zed, cls.s_10, cls.s_100, cls.s_none]

    def setUp(self):
        self.client.force_login(self.user)


class HelperOrderTests(RegisterRollOrderFixture):
    def test_get_exam_students_numeric_roll_none_last(self):
        """The shared exam cohort helper is numeric roll order, None last."""
        self.assertEqual(
            [s.pk for s in get_exam_students(self.exam)],
            [s.pk for s in self.register_rolls()],
        )

    def test_failed_subject_rows_numeric_roll_none_last(self):
        """Subject Fail List rows: subject code, then numeric roll, None last."""
        # Turn every mark into a fail (pass mark for 100 full is 33).
        for student in (self.s_10, self.s_2, self.s_100, self.s_none):
            mark = ExamMark.objects.get(exam=self.exam, student=student)
            mark.marks_obtained = {self.s_10.pk: 10, self.s_2.pk: 20,
                                   self.s_100.pk: 5, self.s_none.pk: 1}[student.pk]
            mark.save(update_fields=['marks_obtained'])
        rows = failed_subject_rows(self.exam)
        rolls = [row['student'].roll_no for row in rows]
        self.assertEqual(rolls, [2, 10, 100, None])

    def test_section_arrangement_stays_merit_based(self):
        """Arrangement is a merit output: fewer fails first — rolls never sort it."""
        rows = section_arrangement_rows(self.exam)
        # All pass with distinct totals → merit = totals descending: roll 10 first.
        self.assertEqual(rows[0]['student'].pk, self.s_10.pk)
        self.assertEqual(rows[-1]['student'].pk, self.s_none.pk)


class StudentListOrderTests(RegisterRollOrderFixture):
    def test_student_list_page_numeric_roll_none_last(self):
        response = self.client.get(reverse('student_list') + '?admission_class=6&section=A')
        self.assertEqual(response.status_code, 200)
        rolls = [s.roll_no for s in response.context['students']]
        self.assertEqual(rolls, [2, 7, 7, 10, 100, None])
        # Same-roll pair is tie-broken by name, not creation order.
        names = [s.name for s in response.context['students'] if s.roll_no == 7]
        self.assertEqual(names, ['Abe Tie', 'Zed Tie'])

    def test_download_student_list_excel_same_numeric_order(self):
        """Excel export carries exactly the page order (owner decision: roll)."""
        response = self.client.get(
            reverse('download_student_list') + f'?institution={self.institution.pk}&admission_class=6&section=A'
        )
        self.assertEqual(response.status_code, 200)
        from openpyxl import load_workbook
        sheet = load_workbook(BytesIO(response.content)).active
        rolls = [row[4] for row in sheet.iter_rows(min_row=2, values_only=True)]
        self.assertEqual(rolls, [2, 7, 7, 10, 100, None])
        names = [row[1] for row in sheet.iter_rows(min_row=2, values_only=True) if row[4] == 7]
        self.assertEqual(names, ['Abe Tie', 'Zed Tie'])

    def test_student_list_pagination_spans_pages_without_duplicates_or_skips(self):
        """105 rolls over two pages: numeric across the page break, no dupes/skips."""
        students = [
            Student(
                institution=self.institution, student_id=f'PB{roll:03d}', form_no=f'PB{roll:03d}',
                name=f'Page Bulk {roll:03d}', admission_class='6', section='B', roll_no=roll,
                guardian_contact_no='01900000000',
            )
            for roll in range(1, 106)
        ]
        Student.objects.bulk_create(students)
        seen = []
        for page in (1, 2):
            response = self.client.get(
                reverse('student_list') + f'?admission_class=6&section=B&page={page}'
            )
            self.assertEqual(response.status_code, 200)
            seen.extend(s.roll_no for s in response.context['students'])
        self.assertEqual(seen, list(range(1, 106)))
        self.assertEqual(len(seen), len(set(seen)))

    def test_class_attendance_list_numeric_roll_none_last(self):
        """The class-wise attendance entry list follows the paper register."""
        from datetime import date
        response = self.client.get(reverse(
            'mark_attendance_bulk',
            kwargs={'date_str': date.today().isoformat(), 'admission_class': '6',
                    'section': 'A', 'mark_type': 'STUDENT'},
        ))
        self.assertEqual(response.status_code, 200)
        rolls = [s.roll_no for s in response.context['students']]
        self.assertEqual(rolls, [2, 7, 7, 10, 100, None])


class ResultOrderTests(RegisterRollOrderFixture):
    def _build_positions(self):
        from .result_utils import build_exam_results
        _, results = build_exam_results(self.exam)
        return {row['student'].pk: row['position'] for row in results}

    def test_result_sheet_register_order_merit_positions_preserved(self):
        expected = self._build_positions()
        response = self.client.get(reverse('result_sheet', args=[self.exam.pk]))
        self.assertEqual(response.status_code, 200)
        rows = response.context['results']
        self.assertEqual([r['student'].roll_no for r in rows], [2, 7, 7, 10, 100, None])
        self.assertEqual(
            {r['student'].pk: r['position'] for r in rows}, expected,
            'register order must not disturb merit positions',
        )

    def test_exam_result_summary_stays_in_merit_position_order(self):
        """Ranking output: position order is intentional (Position column first)."""
        response = self.client.get(reverse('exam_result_summary', args=[self.exam.pk]))
        self.assertEqual(response.status_code, 200)
        rows = response.context['results']
        self.assertEqual([r['student'].roll_no for r in rows], [10, 2, 100, 7, 7, None])
        self.assertEqual([r['position'] for r in rows], [1, 2, 3, 4, 5, 6])

    def test_exam_result_summary_unranked_tail_follows_ranked_rows(self):
        """Fail / No Marks students have no position and trail the ranked list."""
        ExamMark.objects.filter(exam=self.exam, student=self.s_2).delete()
        response = self.client.get(reverse('exam_result_summary', args=[self.exam.pk]))
        rows = response.context['results']
        ranked = [r['position'] for r in rows if r['position']]
        self.assertEqual(ranked, sorted(ranked))
        self.assertIsNone(rows[-1]['position'])
        self.assertEqual(rows[-1]['student'].pk, self.s_2.pk)

    def test_full_rank_list_merit_order_intentional(self):
        response = self.client.get(reverse('full_rank_list', args=[self.exam.pk]))
        self.assertEqual(response.status_code, 200)
        rows = response.context['results']
        self.assertEqual([r['position'] for r in rows], [1, 2, 3, 4, 5, 6])
        self.assertEqual(rows[0]['student'].roll_no, 10, 'merit, not numeric roll')

    def test_top_10_merit_order_intentional(self):
        response = self.client.get(reverse('top_10', args=[self.exam.pk]))
        self.assertEqual(response.status_code, 200)
        rows = response.context['results']
        self.assertEqual([r['position'] for r in rows], [1, 2, 3, 4, 5, 6])
        self.assertEqual(rows[0]['student'].roll_no, 10, 'merit, not numeric roll')


class PrintOrderTests(RegisterRollOrderFixture):
    def test_seat_plan_assigns_and_prints_in_register_order(self):
        response = self.client.post(
            reverse('generate_seat_plan', args=[self.exam.pk]),
            {'room_config': 'Hall A,INDOOR,10'},
        )
        self.assertRedirects(response, reverse('seat_plan_list', args=[self.exam.pk]))
        self.assertEqual(SeatPlan.objects.filter(exam=self.exam).count(), 6)
        room_response = self.client.get(
            reverse('view_seat_plan_room', args=[self.exam.pk, 'Hall A'])
        )
        self.assertEqual(room_response.status_code, 200)
        seats = list(room_response.context['seats'])
        self.assertEqual([seat.seat_no for seat in seats], [1, 2, 3, 4, 5, 6])
        self.assertEqual([seat.student.roll_no for seat in seats], [2, 7, 7, 10, 100, None])

        signature = self.client.get(
            reverse('signature_sheet', args=[self.exam.pk, 'Hall A'])
        )
        self.assertEqual(signature.status_code, 200)
        self.assertEqual(
            [seat.student.roll_no for seat in signature.context['seats']],
            [2, 7, 7, 10, 100, None],
        )

    def test_class_result_cards_print_run_in_register_order(self):
        # "Print the complete class in one run" — owner decision: roll order.
        response = self.client.get(
            reverse('result_analysis_result_cards') + f'?exam={self.exam.pk}'
        )
        self.assertEqual(response.status_code, 200)
        rows = response.context['results']
        self.assertEqual([r['student'].roll_no for r in rows], [2, 7, 7, 10, 100, None])
        # Each card still carries its computed merit position.
        self.assertEqual(rows[0]['position'], 2)
        self.assertEqual([r['position'] for r in rows], [2, 4, 5, 1, 3, 6])

    def test_multi_term_rows_in_register_order(self):
        response = self.client.get(
            reverse('result_analysis_multi_term'),
            {'exams': [self.exam.pk, self.exam2.pk]},
        )
        self.assertEqual(response.status_code, 200)
        rolls = [row['student'].roll_no for row in response.context['rows']]
        self.assertEqual(rolls, [2, 7, 7, 10, 100, None])
