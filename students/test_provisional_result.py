"""Provisional result — seeing a result while 1-2 subjects are still unmarked.

The office question this pins down:

    ১০ বিষয়ের পরীক্ষা, ৮/৯ বিষয়ের নম্বর দেওয়া হয়েছে, বাকি ১/২ বিষয়ের নম্বর
    এখনো দেওয়া যায়নি — রেজাল্ট দেখা দরকার। কিন্তু ১০ বিষয়েই রেজাল্ট দিতে
    হয় বলে অফিসিয়াল শিটে সবার F আসবে।

The official reading is deliberately *not* changed here: a blank assigned
subject is F/0 (``EXAM_ABSENT_SUBJECT_FAILS``) on every published surface.
What is added is a separate, read-only **provisional** sheet
(:func:`students.result_utils.build_exam_results` with ``provisional=True`` and
the ``result_provisional`` view) that treats a blank as "not entered yet":

* unmarked assigned subjects stay visible as columns,
* a blank cell is ``pending`` and out of total/%/GPA/pass-fail,
* an entered 0 or an entered low mark is still a real Fail,
* position is withheld for anyone with a pending subject,
* the page works before publishing and changes nothing.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Exam, ExamMark, Institution, Student, Subject, SubjectRequirement
from .result_utils import build_exam_results


def _row(results, student):
    return next(row for row in results if row['student'].pk == student.pk)


class ProvisionalResultTests(TestCase):
    def setUp(self):
        self.institution = Institution.objects.create(name='Provisional School', classes='9')
        self.user = get_user_model().objects.create_superuser(
            username='provisional-admin', password='password',
        )
        self.client.force_login(self.user)
        self.physics = Subject.objects.create(code='PHY', name='Physics', full_marks=100)
        self.math = Subject.objects.create(code='MTH', name='Mathematics', full_marks=100)
        self.chemistry = Subject.objects.create(code='CHM', name='Chemistry', full_marks=100)
        for subject in (self.physics, self.math, self.chemistry):
            SubjectRequirement.objects.create(
                institution=self.institution, admission_class='9', group='',
                subject=subject, requirement_type='MANDATORY',
            )
        self.exam = Exam.objects.create(
            name='Half Entered Examination-2026', exam_type='SECOND_TERM',
            institution=self.institution, admission_class='9', session='2026',
        )
        self.complete = Student.objects.create(
            institution=self.institution, student_id='P1', name='Complete Student',
            admission_class='9', section='A', roll_no=1, admission_year=2026,
        )
        self.missing_one = Student.objects.create(
            institution=self.institution, student_id='P2', name='Missing Chemistry',
            admission_class='9', section='A', roll_no=2, admission_year=2026,
        )
        # Physics and Maths are entered for everybody; Chemistry only for the
        # first student — the exact shape that makes the official sheet fail
        # the whole class in Chemistry.
        for student in (self.complete, self.missing_one):
            for subject in (self.physics, self.math):
                ExamMark.objects.create(
                    exam=self.exam, student=student, subject=subject, marks_obtained=80,
                )
        ExamMark.objects.create(
            exam=self.exam, student=self.complete, subject=self.chemistry, marks_obtained=80,
        )

    # ---- the official reading is untouched -------------------------------

    def test_official_result_still_fails_a_blank_subject(self):
        _columns, results = build_exam_results(self.exam)
        row = _row(results, self.missing_one)
        self.assertEqual(row['status'], 'Fail')
        self.assertEqual(row['gpa'], Decimal('0.00'))
        self.assertEqual(row['absent_subject_count'], 1)
        chemistry = next(
            cell for cell in row['subject_results'] if cell['subject'].pk == self.chemistry.pk
        )
        self.assertEqual(chemistry['grade'], 'F')
        self.assertFalse(chemistry.get('pending'))

    # ---- the provisional reading ------------------------------------------

    def test_provisional_leaves_pending_subject_out_of_total_and_gpa(self):
        _columns, results = build_exam_results(self.exam, provisional=True)
        row = _row(results, self.missing_one)
        self.assertEqual(row['status'], 'Pending')
        self.assertEqual(row['pending_subject_count'], 1)
        self.assertEqual(row['counted_subject_count'], 2)
        self.assertEqual(row['applicable_subject_count'], 3)
        # 80 + 80 out of 100 + 100 — Chemistry is not counted at all.
        self.assertEqual(row['total_obtained'], Decimal('160'))
        self.assertEqual(row['percentage'], 80.0)
        self.assertNotEqual(row['status'], 'Fail')
        chemistry = next(
            cell for cell in row['subject_results'] if cell['subject'].pk == self.chemistry.pk
        )
        self.assertTrue(chemistry['pending'])
        self.assertIsNone(chemistry['obtained'])

    def test_a_subject_with_no_marks_at_all_stays_a_visible_column(self):
        SubjectRequirement.objects.create(
            institution=self.institution, admission_class='9', group='',
            subject=Subject.objects.create(code='BIO', name='Biology', full_marks=100),
            requirement_type='MANDATORY',
        )
        official_columns, _results = build_exam_results(self.exam)
        provisional_columns, _results = build_exam_results(self.exam, provisional=True)
        official_codes = {column.code for column in official_columns}
        provisional_codes = {column.code for column in provisional_columns}
        self.assertNotIn('BIO', official_codes)
        self.assertIn('BIO', provisional_codes)

    def test_provisional_never_hides_a_real_fail_or_a_real_zero(self):
        ExamMark.objects.filter(
            exam=self.exam, student=self.missing_one, subject=self.math,
        ).update(marks_obtained=0)
        _columns, results = build_exam_results(self.exam, provisional=True)
        row = _row(results, self.missing_one)
        self.assertEqual(row['status'], 'Fail')
        self.assertIsNone(row['position'])

    def test_position_is_withheld_for_students_with_pending_papers(self):
        _columns, results = build_exam_results(self.exam, provisional=True)
        complete_row = _row(results, self.complete)
        pending_row = _row(results, self.missing_one)
        self.assertEqual(complete_row['status'], 'Pass')
        self.assertEqual(complete_row['position'], 1)
        self.assertEqual(pending_row['status'], 'Pending')
        self.assertIsNone(pending_row['position'])

    def test_a_student_with_nothing_entered_is_still_no_marks(self):
        blank_student = Student.objects.create(
            institution=self.institution, student_id='P3', name='Nothing Entered',
            admission_class='9', section='A', roll_no=3, admission_year=2026,
        )
        _columns, results = build_exam_results(self.exam, provisional=True)
        row = _row(results, blank_student)
        self.assertEqual(row['status'], 'No Marks')
        self.assertFalse(row['has_marks'])

    # ---- the page --------------------------------------------------------

    def test_page_works_on_an_unpublished_exam_and_names_the_pending_subject(self):
        self.assertFalse(self.exam.is_published)
        response = self.client.get(reverse('result_provisional', args=[self.exam.pk]))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn('Provisional result', body)
        # Chemistry is the one missing marks — named on the page, with the
        # number of students it is missing for.
        self.assertIn('Chemistry', body)
        self.assertIn('1 of 2', body)
        self.assertFalse(response.context['complete'])
        self.assertEqual(response.context['subject_count'], 3)
        self.assertEqual(response.context['ready_subject_count'], 2)

    def test_page_reports_complete_when_every_subject_has_marks(self):
        for student in (self.complete, self.missing_one):
            ExamMark.objects.update_or_create(
                exam=self.exam, student=student, subject=self.chemistry,
                defaults={'marks_obtained': 70},
            )
        response = self.client.get(reverse('result_provisional', args=[self.exam.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['complete'])
        self.assertEqual(response.context['pending_columns'], [])
        self.assertIn('All 3 subjects have marks', response.content.decode())

    def test_page_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse('result_provisional', args=[self.exam.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response['Location'])

    def test_exam_list_links_to_the_provisional_page(self):
        response = self.client.get(reverse('exam_list'))
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            reverse('result_provisional', args=[self.exam.pk]),
            response.content.decode(),
        )
