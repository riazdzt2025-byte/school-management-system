"""Top Ten sheet — the school's "Top Ten (10)" printout.

The page is the office's merit printout: the shared portrait letterhead and
class info box, ten rows in merit order with the columns Roll No. / ID No. /
Student Name / Grade / GP / Total / Place / A Plus / Fail / Comments, where

* **Place** prints as an ordinal (1st, 2nd, 3rd, … 10th) — merit order, not
  register order, is this page's identity;
* **A Plus** is the student's A+ subject count and **Fail** the failed subject
  count;
* **Comments** marks ``Golden`` (A+ in every graded paper) and ``Potential``
  (exactly one paper away from that);

and the Controller of Exam / Head Teacher signatures close the sheet.
"""
import re

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Exam, ExamMark, Institution, Student, Subject, SubjectRequirement


class TopTenSheetTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.institution = Institution.objects.create(name='Top Ten School', classes='6')
        cls.user = get_user_model().objects.create_superuser('topten-admin', 't@example.com', 'password')
        cls.subjects = [
            Subject.objects.create(code=f'TT{index}', name=f'Paper {index}', full_marks=100)
            for index in range(1, 4)
        ]
        for subject in cls.subjects:
            SubjectRequirement.objects.create(
                institution=cls.institution, admission_class='6', subject=subject,
                requirement_type='MANDATORY',
            )
        cls.exam = Exam.objects.create(
            name='Mid Term-3', exam_type='MID_TERM_3', institution=cls.institution,
            admission_class='6', section='A', session='2025-2026', is_published=True,
        )
        # Roll order is deliberately the reverse of the merit order.
        cls.golden = Student.objects.create(
            institution=cls.institution, student_id='TT001', name='Golden Student',
            admission_class='6', section='A', roll_no=30, admission_year=2026,
        )
        cls.potential = Student.objects.create(
            institution=cls.institution, student_id='TT002', name='Potential Student',
            admission_class='6', section='A', roll_no=20, admission_year=2026,
        )
        cls.plain = Student.objects.create(
            institution=cls.institution, student_id='TT003', name='Plain Student',
            admission_class='6', section='A', roll_no=10, admission_year=2026,
        )
        marks = []
        for subject_index, subject in enumerate(cls.subjects):
            marks.extend([
                # A+ everywhere -> Golden, GPA 5.00, place 1.
                ExamMark(exam=cls.exam, student=cls.golden, subject=subject, marks_obtained=90),
                # One paper below A+ -> Potential, place 2.
                ExamMark(exam=cls.exam, student=cls.potential, subject=subject,
                         marks_obtained=70 if subject_index == 0 else 90),
                # Two papers below A+ -> no comment, place 3.
                ExamMark(exam=cls.exam, student=cls.plain, subject=subject,
                         marks_obtained=70 if subject_index < 2 else 90),
            ])
        ExamMark.objects.bulk_create(marks)

    def setUp(self):
        self.client.force_login(self.user)

    def get_page(self):
        response = self.client.get(reverse('top_10', args=[self.exam.pk]))
        self.assertEqual(response.status_code, 200)
        return response, response.content.decode('utf-8')

    def rows(self, html):
        body = html.split('<tbody>', 1)[1].split('</tbody>', 1)[0]
        return [
            [re.sub(r'<[^>]+>', '', cell).strip() for cell in re.findall(r'<td[^>]*>(.*?)</td>', row, re.S)]
            for row in re.findall(r'<tr>(.*?)</tr>', body, re.S)
        ]

    def test_columns_match_the_printed_sheet(self):
        _response, html = self.get_page()
        self.assertEqual(
            [cell.strip() for cell in re.findall(r'<th>(.*?)</th>', html, re.S)],
            ['Roll No.', 'ID No.', 'Student Name', 'Grade', 'GP', 'Total',
             'Place', 'A Plus', 'Fail', 'Comments'],
        )

    def test_rows_keep_merit_order_and_print_ordinal_places(self):
        _response, html = self.get_page()
        self.assertEqual(
            self.rows(html),
            [
                ['30', 'TT001', 'Golden Student', 'A+', '5.00', '270', '1st', '3', '0', 'Golden'],
                ['20', 'TT002', 'Potential Student', 'A+', '4.67', '250', '2nd', '2', '0', 'Potential'],
                ['10', 'TT003', 'Plain Student', 'A', '4.33', '230', '3rd', '1', '0', ''],
            ],
        )

    def test_letterhead_info_box_and_title(self):
        _response, html = self.get_page()
        self.assertIn('<h1 class="pr-school">Principal Kazi Faruky School</h1>', html)
        self.assertIn('Top Ten (10)', html)
        self.assertIn('<td class="pr-info-label">Year</td><td>2026</td>', html)
        self.assertIn('<td class="pr-info-label">Class</td><td>06 (Six)</td>', html)
        self.assertIn('<td class="pr-info-label">Section/Group</td><td>A</td>', html)
        # All three students pass; one is a Golden A Plus.
        self.assertIn('<td class="pr-info-label">Pass Rate in Class</td><td>100 %</td>', html)
        self.assertIn('<td class="pr-info-label">Golden A Plus</td><td>1</td>', html)

    def test_sheet_ends_with_the_two_signatures(self):
        _response, html = self.get_page()
        self.assertEqual(html.count('Controller of Exam'), 1)
        signs = html.split('class="pr-sign-row"', 1)[1]
        self.assertIn('Guide Teacher', signs)
        self.assertIn('Controller of Exam', signs)
        self.assertIn('Head Teacher', signs)
        # Guide Teacher leads the row: the school's signatures sit to its right.
        self.assertLess(signs.index('Guide Teacher'), signs.index('Controller of Exam'))
        self.assertLess(html.index('Plain Student'), html.index('class="pr-sign-row"'))

    def test_sheet_prints_on_a4_portrait(self):
        _response, html = self.get_page()
        self.assertIn('@page { size: A4 portrait', html)
        self.assertNotIn('A4 landscape', html)

    def test_only_ranked_students_are_listed_and_capped_at_ten(self):
        # Fail this student: an unranked result must never appear on a merit sheet.
        ExamMark.objects.filter(exam=self.exam, student=self.plain).update(marks_obtained=10)
        response, html = self.get_page()
        self.assertEqual(len(response.context['results']), 2)
        self.assertNotIn('Plain Student', html)

    def test_comments_mark_golden_and_one_paper_away_only(self):
        _response, html = self.get_page()
        self.assertEqual(html.count('>Golden<'), 1)
        self.assertEqual(html.count('>Potential<'), 1)

    def test_unpublished_exam_redirects(self):
        self.exam.is_published = False
        self.exam.save(update_fields=['is_published'])
        response = self.client.get(reverse('top_10', args=[self.exam.pk]))
        self.assertRedirects(response, reverse('exam_list'))
