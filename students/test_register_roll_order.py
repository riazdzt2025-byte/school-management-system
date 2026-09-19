"""EX-02 — register (roll) order vs merit order, pinned for every list/print/export.

The rule this file pins, in one line:

    register-flavoured output  -> numeric roll order  (roll None last, then
                                  name, then pk)
    merit/rank output          -> position order      (top_10, full_rank_list)

Roll ``2``, ``10``, ``100`` and ``None`` are the trap: as text they sort
``'10' < '100' < '2'``, so any output that loses the numeric sort (or any
``Student.roll_no`` treated as a string) shows the register in the wrong order.
The students below are also named so that alphabetical order is *different*
from roll order — an alphabetical list would fail every assertion here.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import (
    Exam, ExamMark, Institution, SeatPlan, Student, Subject, SubjectRequirement,
)
from .result_utils import build_exam_results, roll_order_key, roll_order_queryset

try:
    import openpyxl
except ImportError:  # pragma: no cover - openpyxl is optional in this sandbox
    openpyxl = None

from io import BytesIO


# Roll -> (name, marks). Marks are deliberately the reverse of the roll order:
# the best student sits on the highest roll, so a merit sort and a roll sort
# produce two visibly different lists.
REGISTER = (
    (2, 'Zeta', 60),
    (10, 'Alpha', 50),
    (100, 'Mu', 95),
    (None, 'Beta', 70),
)


class RollOrderFixture(TestCase):
    """One published exam, four students whose roll/name/merit orders differ."""

    @classmethod
    def setUpTestData(cls):
        cls.institution = Institution.objects.create(name='Roll Order School', classes='6')
        cls.user = get_user_model().objects.create_superuser(
            username='roll-admin', password='password',
        )
        cls.bangla = Subject.objects.create(code='BAN1', name='Bangla 1st Paper', full_marks=100)
        cls.english = Subject.objects.create(code='ENG1', name='English 1st Paper', full_marks=100)
        for subject in (cls.bangla, cls.english):
            SubjectRequirement.objects.create(
                institution=cls.institution, admission_class='6', subject=subject,
                requirement_type='MANDATORY',
            )
        cls.exam = Exam.objects.create(
            name='Second Term Examination-2026', exam_type='SECOND_TERM',
            institution=cls.institution, admission_class='6', section='A',
            session='2026', is_published=True,
        )
        cls.students = {}
        for roll, name, mark in REGISTER:
            student = Student.objects.create(
                institution=cls.institution, student_id=f'ROLL{name.upper()}',
                name=name, admission_class='6', section='A', roll_no=roll,
                admission_year=2026,
            )
            for subject in (cls.bangla, cls.english):
                ExamMark.objects.create(
                    exam=cls.exam, student=student, subject=subject, marks_obtained=mark,
                )
            cls.students[name] = student

    def setUp(self):
        self.client.force_login(self.user)

    @staticmethod
    def rolls(rows):
        return [row['student'].roll_no for row in rows]

    @property
    def roll_order(self):
        return [2, 10, 100, None]

    @property
    def merit_order(self):
        """Student names best-first (roll 100 > None > 2 > 10 by marks)."""
        return ['Mu', 'Beta', 'Zeta', 'Alpha']


class RegisterOutputOrderTests(RollOrderFixture):
    """Register/roll outputs: numeric roll order, no roll last."""

    def test_result_sheet_is_in_numeric_roll_order(self):
        response = self.client.get(reverse('result_sheet', args=[self.exam.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.rolls(response.context['results']), self.roll_order)

    def test_result_sheet_roll_order_keeps_merit_positions(self):
        """Re-sorting the register must not move anyone's position."""
        _columns, ranked = build_exam_results(self.exam)
        expected = {row['student'].pk: row['position'] for row in ranked}
        response = self.client.get(reverse('result_sheet', args=[self.exam.pk]))
        self.assertEqual(
            {row['student'].pk: row['position'] for row in response.context['results']},
            expected,
        )
        # All four pass, so the places (Mu 1, Beta 2, Zeta 3, Alpha 4) travel
        # with their rows into roll order instead of being re-numbered 1-4.
        self.assertEqual(
            [row['position'] for row in response.context['results']], [3, 4, 1, 2],
        )

    def test_published_result_summary_is_in_numeric_roll_order(self):
        response = self.client.get(reverse('exam_result_summary', args=[self.exam.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.rolls(response.context['results']), self.roll_order)

    def test_published_result_summary_page_prints_rolls_in_order(self):
        response = self.client.get(reverse('exam_result_summary', args=[self.exam.pk]))
        content = response.content.decode()
        # Student IDs, not names: a name can occur earlier in the page chrome.
        printed = [
            content.index(student_id)
            for student_id in ('ROLLZETA', 'ROLLALPHA', 'ROLLMU', 'ROLLBETA')
        ]
        self.assertEqual(printed, sorted(printed))

    def test_class_result_cards_are_in_numeric_roll_order(self):
        response = self.client.get(
            reverse('result_analysis_result_cards'), {'exam': self.exam.pk},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.rolls(response.context['results']), self.roll_order)

    def test_student_list_is_in_numeric_roll_order(self):
        response = self.client.get(reverse('student_list'), {
            'institution': self.institution.pk, 'admission_class': '6', 'section': 'A',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [student.roll_no for student in response.context['students']], self.roll_order,
        )

    def test_excel_export_is_in_numeric_roll_order(self):
        if openpyxl is None:
            self.skipTest('openpyxl is not installed')
        response = self.client.get(reverse('download_student_list'), {
            'institution': self.institution.pk, 'admission_class': '6', 'section': 'A',
        })
        self.assertEqual(response.status_code, 200)
        workbook = openpyxl.load_workbook(BytesIO(response.content))
        sheet = workbook.active
        header = [cell.value for cell in sheet[1]]
        roll_column = header.index('Roll No')
        self.assertEqual(
            [row[roll_column] for row in sheet.iter_rows(min_row=2, values_only=True)],
            self.roll_order,
        )

    def test_attendance_class_list_is_in_numeric_roll_order(self):
        response = self.client.get(reverse('mark_attendance_bulk', kwargs={
            'date_str': '2026-09-19', 'admission_class': '6', 'section': 'A',
            'mark_type': 'STUDENT',
        }))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [student.roll_no for student in response.context['students']], self.roll_order,
        )

    def test_seat_plan_is_allocated_in_numeric_roll_order(self):
        response = self.client.post(reverse('generate_seat_plan', args=[self.exam.pk]), {
            'room_config': 'Room 1, INDOOR, 4',
        })
        self.assertEqual(response.status_code, 302)
        seats = SeatPlan.objects.filter(exam=self.exam).order_by('room_name', 'seat_no')
        self.assertEqual([seat.student.roll_no for seat in seats], self.roll_order)

    def test_seat_plan_room_lists_seats_in_seat_order(self):
        self.client.post(reverse('generate_seat_plan', args=[self.exam.pk]), {
            'room_config': 'Room 1, INDOOR, 4',
        })
        response = self.client.get(
            reverse('view_seat_plan_room', args=[self.exam.pk, 'Room 1']),
        )
        self.assertEqual(response.status_code, 200)
        seats = list(response.context['seats'])
        self.assertEqual([seat.seat_no for seat in seats], [1, 2, 3, 4])
        self.assertEqual([seat.student.roll_no for seat in seats], self.roll_order)

    def test_signature_sheet_follows_the_generated_seat_order(self):
        self.client.post(reverse('generate_seat_plan', args=[self.exam.pk]), {
            'room_config': 'Room 1, INDOOR, 4',
        })
        response = self.client.get(
            reverse('signature_sheet', args=[self.exam.pk, 'Room 1']),
        )
        self.assertEqual(response.status_code, 200)
        seats = list(response.context['seats'])
        self.assertEqual([seat.seat_no for seat in seats], [1, 2, 3, 4])
        self.assertEqual([seat.student.roll_no for seat in seats], self.roll_order)


class MeritOutputOrderTests(RollOrderFixture):
    """Merit outputs stay in position order — deliberately not roll order."""

    def test_full_rank_list_is_in_merit_order(self):
        response = self.client.get(reverse('full_rank_list', args=[self.exam.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [row['student'].name for row in response.context['results']], self.merit_order,
        )
        self.assertEqual([row['position'] for row in response.context['results']], [1, 2, 3, 4])

    def test_full_rank_list_puts_unplaced_students_last_in_roll_order(self):
        """A failed result has no position, so it falls back to register order."""
        failed = Student.objects.create(
            institution=self.institution, student_id='ROLLFAIL', name='Delta',
            admission_class='6', section='A', roll_no=7, admission_year=2026,
        )
        for subject in (self.bangla, self.english):
            ExamMark.objects.create(
                exam=self.exam, student=failed, subject=subject, marks_obtained=5,
            )
        response = self.client.get(reverse('full_rank_list', args=[self.exam.pk]))
        self.assertEqual(
            [row['student'].name for row in response.context['results']], self.merit_order,
        )
        self.assertEqual(
            [row['student'].roll_no for row in response.context['unranked_results']], [7],
        )

    def test_top_10_is_in_merit_order(self):
        response = self.client.get(reverse('top_10', args=[self.exam.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [row['student'].name for row in response.context['results']], self.merit_order,
        )

    def test_result_sheet_roll_order_differs_from_merit_order(self):
        """Guard against both lists quietly collapsing into one ordering."""
        response = self.client.get(reverse('result_sheet', args=[self.exam.pk]))
        roll_names = [row['student'].name for row in response.context['results']]
        self.assertEqual(roll_names, ['Zeta', 'Alpha', 'Mu', 'Beta'])
        self.assertNotEqual(roll_names, self.merit_order)


class RollOrderHelperTests(RollOrderFixture):
    """The shared helper: numeric, no-roll last, stable ties."""

    def test_helper_matches_the_queryset_order_on_every_student(self):
        queryset_order = [s.pk for s in roll_order_queryset(
            Student.objects.filter(institution=self.institution),
        )]
        helper_order = [s.pk for s in sorted(
            Student.objects.filter(institution=self.institution), key=roll_order_key,
        )]
        self.assertEqual(helper_order, queryset_order)

    def test_students_without_a_roll_come_last(self):
        pks = [s.pk for s in roll_order_queryset(
            Student.objects.filter(institution=self.institution),
        )]
        self.assertEqual(pks[-1], self.students['Beta'].pk)

    def test_duplicate_rolls_keep_a_stable_order(self):
        first = Student.objects.create(
            institution=self.institution, student_id='DUPA', name='Same Roll A',
            admission_class='6', section='A', roll_no=5, admission_year=2026,
        )
        second = Student.objects.create(
            institution=self.institution, student_id='DUPB', name='Same Roll B',
            admission_class='6', section='A', roll_no=5, admission_year=2026,
        )
        first_response = self.client.get(reverse('student_list'), {
            'institution': self.institution.pk, 'admission_class': '6', 'section': 'A',
        })
        second_response = self.client.get(reverse('student_list'), {
            'institution': self.institution.pk, 'admission_class': '6', 'section': 'A',
        })
        first_ids = [student.pk for student in first_response.context['students']]
        second_ids = [student.pk for student in second_response.context['students']]
        self.assertEqual(first_ids, second_ids)
        self.assertEqual(first_ids.index(first.pk) + 1, first_ids.index(second.pk))
        # And they sit together, after roll 2 and before roll 10.
        self.assertEqual(first_ids[1:3], [first.pk, second.pk])
