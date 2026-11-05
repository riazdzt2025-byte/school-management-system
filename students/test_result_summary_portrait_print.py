"""Published Result (``result_summary``) — portrait A4 print layout.

The Published Result register is printed and filed, so it has to fit paper:
portrait A4 (not the landscape Full Mark Sheet), a header strip naming the
school, exam and class on every printed sheet, one register row per student
that never splits across a page break, the same nine printed columns in the
same order as the screen table, and a footer with "Page x of y", the print
date and the print user.

Screen behaviour is unchanged on purpose: the paginated dashboard table, the
Details / Card actions and the pagination controls stay exactly as they were.
"""
import re
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import (
    Exam, ExamMark, Institution, InstitutionAccess, Student, Subject, SubjectRequirement,
)


class PublishedResultPrintLayoutTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.institution = Institution.objects.create(name='Portrait Print School', classes='6')
        cls.user = get_user_model().objects.create_superuser('print-admin', 'p@example.com', 'password')
        cls.subject = Subject.objects.create(code='PRB1', name='Bangla', full_marks=100)
        SubjectRequirement.objects.create(
            institution=cls.institution, admission_class='6', subject=cls.subject,
            requirement_type='MANDATORY',
        )
        cls.exam = Exam.objects.create(
            name='Mid Term-3', exam_type='MID_TERM_3', institution=cls.institution,
            admission_class='6', section='A', session='2025-2026', is_published=True,
        )
        cls.students = [
            Student.objects.create(
                institution=cls.institution, student_id=f'PP{roll:03d}', name=f'Student {roll}',
                admission_class='6', section='A', roll_no=roll, admission_year=2026,
            )
            for roll in (1, 2, 3, 4, 5)
        ]
        ExamMark.objects.bulk_create([
            ExamMark(exam=cls.exam, student=student, subject=cls.subject, marks_obtained=80 - 10 * (student.roll_no - 1))
            for student in cls.students
        ])

    def setUp(self):
        self.client.force_login(self.user)

    def get_page(self, **params):
        response = self.client.get(reverse('exam_result_summary', args=[self.exam.pk]), params)
        self.assertEqual(response.status_code, 200)
        return response, response.content.decode('utf-8')

    # ------------------------------------------------------------------- paper
    def test_page_is_a4_portrait_not_landscape(self):
        _response, html = self.get_page()
        self.assertIn('@page { size: A4 portrait', html)
        self.assertNotIn('A4 landscape', html)

    def test_rows_never_split_across_a_page_break(self):
        _response, html = self.get_page()
        self.assertIn('break-inside: avoid', html)
        self.assertIn('page-break-inside: avoid', html)
        # The header row repeats on every printed sheet.
        self.assertIn('display: table-header-group', html)

    def test_shared_dashboard_print_header_is_suppressed(self):
        """The sheet has its own letterhead; the generic one must not repeat."""
        _response, html = self.get_page()
        self.assertIn('.main > .print-header { display: none !important; }', html)

    # ------------------------------------------------- screen keeps its identity
    def test_screen_view_keeps_the_paginated_dashboard_table(self):
        response, html = self.get_page()
        self.assertFalse(response.context['is_print_view'])
        self.assertEqual(response.context['print_sheets'], [])
        self.assertNotIn('class="summary-sheet"', html)
        self.assertIn('data-list-pagination', html)
        # The actions column and the coloured status badges stay on screen.
        self.assertIn('class="d-print-none">Action', html)
        self.assertIn('badge bg-success', html)

    def test_screen_view_carries_a_print_only_header_for_ctrl_p(self):
        _response, html = self.get_page()
        self.assertIn('d-none d-print-block', html)
        self.assertIn('Principal Kazi Faruky School', html)
        self.assertIn('Mid Term-3', html)

    # -------------------------------------------------------------- print view
    def test_print_view_is_chunked_into_numbered_sheets(self):
        with mock.patch('students.views.SUMMARY_PRINT_ROWS_PER_PAGE', 2):
            response, html = self.get_page(print=1)
        self.assertTrue(response.context['is_print_view'])
        self.assertEqual(len(response.context['print_sheets']), 3)
        self.assertIn('Page 1 of 3', html)
        self.assertIn('Page 2 of 3', html)
        self.assertIn('Page 3 of 3', html)
        self.assertEqual(html.count('<section class="pr-sheet"'), 3)

    def test_print_view_has_no_ui_pagination(self):
        _response, html = self.get_page(print=1)
        self.assertNotIn('data-list-pagination', html)
        self.assertIn('Back to paginated list', html)

    def test_every_printed_sheet_repeats_the_letterhead_and_column_titles(self):
        with mock.patch('students.views.SUMMARY_PRINT_ROWS_PER_PAGE', 2):
            _response, html = self.get_page(print=1)
        self.assertEqual(html.count('<h1 class="pr-school">Principal Kazi Faruky School</h1>'), 3)
        self.assertEqual(html.count('<th>Roll No.</th>'), 3)
        self.assertEqual(html.count('Pass Rate in Class'), 3)

    def test_print_view_keeps_register_roll_order_and_splits_at_the_sheet_edge(self):
        with mock.patch('students.views.SUMMARY_PRINT_ROWS_PER_PAGE', 2):
            response, _html = self.get_page(print=1)
        sheets = response.context['print_sheets']
        self.assertEqual(
            [[row['student'].roll_no for row in sheet['rows']] for sheet in sheets],
            [[1, 2], [3, 4], [5]],
        )
        self.assertEqual(sheets[-1]['page_no'], 3)

    def test_printed_columns_are_the_screen_columns_without_actions(self):
        response, html = self.get_page(print=1)
        head = html.split('<thead>', 1)[1].split('</thead>', 1)[0]
        headers = [re.sub(r'<[^>]+>', '', cell).strip()
                   for cell in re.findall(r'<th[^>]*>(.*?)</th>', head, re.S)]
        self.assertEqual(
            headers,
            ['Roll No.', 'ID No.', 'Student Name', 'Total', 'Percentage', 'GP',
             'Grade', 'Status', 'Place'],
        )
        self.assertIsNotNone(response.context['print_sheets'])

    def test_printed_status_is_plain_text_not_a_badge(self):
        _response, html = self.get_page(print=1)
        self.assertNotIn('badge bg-success', html)
        self.assertRegex(html, r'<td>Pass</td>')

    def test_footer_carries_page_number_print_date_and_print_user(self):
        with mock.patch('students.views.SUMMARY_PRINT_ROWS_PER_PAGE', 2):
            _response, html = self.get_page(print=1)
        self.assertEqual(html.count('Print User: print-admin'), 3)
        self.assertEqual(html.count('Print Date:'), 3)
        self.assertIn('pr-page-no', html)

    def test_header_strip_reports_class_section_and_truncated_pass_rate(self):
        _response, html = self.get_page(print=1)
        self.assertIn('06 (Six)', html)
        self.assertIn('Section/Group', html)
        self.assertIn('<td class="pr-info-label">Pass Rate in Class</td><td>100 %</td>', html)

    def test_exam_without_students_still_prints_one_sheet(self):
        ExamMark.objects.all().delete()
        Student.objects.all().delete()
        response, html = self.get_page(print=1)
        self.assertEqual(len(response.context['print_sheets']), 1)
        self.assertIn('Page 1 of 1', html)
        self.assertIn('No students found.', html)


class PublishedResultPrintAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.institution = Institution.objects.create(name='Gate School', classes='6')
        cls.user = get_user_model().objects.create_superuser('gate-admin', 'g@example.com', 'password')
        cls.exam = Exam.objects.create(
            name='Gate Exam', exam_type='MID_TERM_3', institution=cls.institution,
            admission_class='6', session='2026', is_published=True,
        )

    def setUp(self):
        self.client.force_login(self.user)

    def test_unpublished_exam_redirects_print_view_to_exam_list(self):
        self.exam.is_published = False
        self.exam.save(update_fields=['is_published'])
        response = self.client.get(
            reverse('exam_result_summary', args=[self.exam.pk]), {'print': 1}
        )
        self.assertRedirects(response, reverse('exam_list'))

    def test_other_institution_exam_is_404_in_print_view(self):
        other = Institution.objects.create(name='Elsewhere School', classes='6')
        foreign_exam = Exam.objects.create(
            name='Foreign', exam_type='MID_TERM_3', institution=other,
            admission_class='6', session='2026', is_published=True,
        )
        # A clerk scoped to one institution must not print another's exam.
        clerk = get_user_model().objects.create_user(username='gate-clerk', password='password')
        InstitutionAccess.objects.create(user=clerk, institution=self.institution, department='Office')
        self.client.force_login(clerk)
        response = self.client.get(reverse('exam_result_summary', args=[foreign_exam.pk]), {'print': 1})
        self.assertEqual(response.status_code, 404)
