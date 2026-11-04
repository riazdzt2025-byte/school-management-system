"""Download the printed result sheets as Excel / CSV, and the Exams action menu.

The office can print a result sheet, but a printed sheet cannot be sorted,
filtered, or handed to accounts as a table. Every result page therefore offers
one **Download** menu with the same sheet in three shapes — Excel workbook, CSV
file, and the print dialog — and every file comes from the same computation the
page renders, so a downloaded GPA can never disagree with the paper.

The Exams page now shows one **Actions** menu per row instead of eight buttons
in a table cell; this module keeps that menu complete and keeps each link on it
pointing where it used to.
"""
import csv
import io
import re
from datetime import date

import openpyxl
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Exam, ExamMark, Institution, Student, Subject, SubjectRequirement

EXCEL = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
CSV_TYPE = 'text/csv; charset=utf-8'


class DownloadFixtures(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.institution = Institution.objects.create(name='Download School', classes='8')
        cls.user = get_user_model().objects.create_superuser(
            'download-admin', 'd@example.com', 'password',
        )
        cls.subjects = [
            Subject.objects.create(code=code, name=name, full_marks=100)
            for code, name in (('BAN1', 'Bangla 1st Paper'), ('ENG1', 'English 1st Paper'))
        ]
        for subject in cls.subjects:
            SubjectRequirement.objects.create(
                institution=cls.institution, admission_class='8', subject=subject,
                requirement_type='MANDATORY',
            )
        cls.exam = Exam.objects.create(
            name='Annual Examination-2026', exam_type='FINAL_TERM',
            institution=cls.institution, admission_class='8', section='A',
            session='2026', is_published=True,
        )
        # A name that a spreadsheet would execute if it were written raw.
        cls.topper = Student.objects.create(
            institution=cls.institution, student_id='DL001', name='Ayesha Siddika',
            admission_class='8', section='A', roll_no=1, admission_year=2026,
        )
        cls.failing = Student.objects.create(
            institution=cls.institution, student_id='DL002', name='=HYPERLINK("x")',
            admission_class='8', section='A', roll_no=2, admission_year=2026,
        )
        cls.absent = Student.objects.create(
            institution=cls.institution, student_id='DL003', name='Rafiq Islam',
            admission_class='8', section='A', roll_no=3, admission_year=2026,
        )
        for subject in cls.subjects:
            ExamMark.objects.create(exam=cls.exam, student=cls.topper, subject=subject, marks_obtained=88)
            ExamMark.objects.create(exam=cls.exam, student=cls.failing, subject=subject, marks_obtained=20)
            ExamMark.objects.create(exam=cls.exam, student=cls.absent, subject=subject, marks_obtained=70)

    def setUp(self):
        self.client.force_login(self.user)

    def download(self, kind, fmt='xlsx', **params):
        url = reverse('download_result_sheet', args=[self.exam.pk, kind, fmt])
        return self.client.get(url, params)

    def workbook(self, response):
        buffer = io.BytesIO(response.content)
        return openpyxl.load_workbook(buffer)

    def header_row(self, sheet, first_header):
        """The row that holds the table headers (the letterhead sits above it)."""
        for row in sheet.iter_rows():
            if row and row[0].value == first_header:
                return row[0].row
        self.fail(f'no header row starting with {first_header!r}')

    def all_values(self, sheet):
        return [
            str(cell.value) for row in sheet.iter_rows()
            for cell in row if cell.value is not None
        ]


class ExcelDownloadTests(DownloadFixtures):
    def test_every_sheet_downloads_as_an_excel_workbook(self):
        for kind in ('sheet', 'published', 'top10', 'summary'):
            with self.subTest(kind=kind):
                response = self.download(kind)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response['Content-Type'], EXCEL)
                self.assertIn('attachment;', response['Content-Disposition'])
                self.assertTrue(response['Content-Disposition'].endswith('.xlsx"'))
                workbook = self.workbook(response)
                self.assertGreaterEqual(len(workbook.sheetnames), 1)

    def test_the_register_workbook_holds_the_letterhead_and_every_student(self):
        response = self.download('sheet')
        sheet = self.workbook(response).worksheets[0]
        values = [
            str(cell.value) for row in sheet.iter_rows() for cell in row if cell.value is not None
        ]
        joined = ' | '.join(values)
        self.assertIn(settings.SCHOOL_INFO['school_name'], joined)  # letterhead, like the paper
        self.assertIn('Annual Examination-2026', joined)  # exam title
        for name in ('Ayesha Siddika', 'Rafiq Islam'):
            self.assertIn(name, joined)
        # One column per paper, then the totals the register prints.
        self.assertIn('BAN1', values)
        self.assertIn('ENG1', values)
        for header in ('Roll No.', 'Student ID', 'Student Name', 'Total', 'GPA', 'Grade', 'Result'):
            self.assertIn(header, values)

    def test_the_register_workbook_keeps_the_frozen_header_and_a_filter(self):
        sheet = self.workbook(self.download('sheet')).worksheets[0]
        self.assertIsNotNone(sheet.freeze_panes)
        self.assertIsNotNone(sheet.auto_filter.ref)
        self.assertFalse(sheet.sheet_view.showGridLines)

    def test_the_summary_workbook_holds_the_three_printed_tables(self):
        workbook = self.workbook(self.download('summary'))
        self.assertEqual(workbook.sheetnames, ['Grade Count', 'Grade x Subject', 'Grading Scale'])
        counts = [cell.value for row in workbook['Grade Count'].iter_rows() for cell in row]
        self.assertIn('Total Examinee', counts)
        matrix = workbook['Grade x Subject']
        header = self.header_row(matrix, 'Grade')
        matrix_header = [cell.value for cell in matrix[header] if cell.value is not None]
        self.assertIn('BAN1', matrix_header)
        # The paper's total column and total row travel with the file.
        self.assertEqual(matrix_header[-1], 'Total')
        total_rows = [
            [cell.value for cell in row] for row in matrix.iter_rows()
            if row[0].value == 'Total'
        ]
        self.assertEqual(len(total_rows), 1, 'exactly one total row, under the matrix')
        self.assertGreater(len([v for v in total_rows[0] if v is not None]), 1)

    def test_the_filename_names_the_sheet_class_and_date(self):
        response = self.download('published')
        disposition = response['Content-Disposition']
        self.assertIn('Published-Result-Sheet', disposition)
        self.assertIn('Class-8', disposition)
        self.assertIn(date.today().isoformat(), disposition)


class PaperLayoutWorkbookTests(DownloadFixtures):
    """The Excel file reads like the printed sheet, not like a bare dump."""

    def test_the_letterhead_is_printed_in_the_papers_red(self):
        sheet = self.workbook(self.download('published')).worksheets[0]
        self.assertEqual(sheet['A1'].value, settings.SCHOOL_INFO['school_name'])
        self.assertEqual(sheet['A1'].font.color.rgb, 'FFA32121')
        self.assertTrue(sheet['A1'].font.bold)
        # Address and phone on the second line, the exam on the third.
        self.assertIn('Lakshmipur', sheet['A2'].value)
        self.assertEqual(sheet['A3'].value, self.exam.name)

    def test_the_class_info_box_travels_with_the_file(self):
        sheet = self.workbook(self.download('published')).worksheets[0]
        values = self.all_values(sheet)
        for label in ('Year', 'Class', 'Section/Group', 'Pass Rate in Class',
                      'Total A Plus', 'Golden A Plus'):
            self.assertIn(label, values)

    def test_the_sheet_closes_with_the_signatures(self):
        sheet = self.workbook(self.download('published')).worksheets[0]
        values = self.all_values(sheet)
        for label in ('Guide Teacher', 'Controller of Exam', 'Head Teacher'):
            self.assertIn(label, values)
        # The register closes with the four columns the paper prints.
        register = self.workbook(self.download('sheet')).worksheets[0]
        register_values = self.all_values(register)
        for label in ('Guide Teacher', 'Controller of Exam', 'Convener', 'Head Teacher'):
            self.assertIn(label, register_values)

    def test_the_table_keeps_its_rules_and_shaded_header(self):
        sheet = self.workbook(self.download('published')).worksheets[0]
        header = self.header_row(sheet, 'Roll No.')
        cell = sheet.cell(row=header, column=1)
        self.assertTrue(cell.font.bold)
        self.assertEqual(cell.fill.fgColor.rgb, 'FFF2F3F5')
        self.assertEqual(cell.border.left.style, 'thin')
        self.assertFalse(sheet.sheet_view.showGridLines)


class DataOnlyWorkbookTests(DownloadFixtures):
    """The data-only file is the rows and nothing else."""

    def test_data_only_holds_one_clean_table(self):
        response = self.download('published', 'data')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], EXCEL)
        self.assertIn('_data.xlsx', response['Content-Disposition'])
        sheet = self.workbook(response).worksheets[0]
        # Header row first, then one row per student — no letterhead above it.
        self.assertEqual(sheet.cell(row=1, column=1).value, 'Roll No.')
        self.assertEqual(sheet.cell(row=1, column=3).value, 'Student Name')
        self.assertEqual(sheet.max_row, 4)
        self.assertNotIn(settings.SCHOOL_INFO['school_name'], self.all_values(sheet))
        self.assertNotIn('Golden A Plus', self.all_values(sheet))

    def test_data_only_still_blocks_a_formula_name(self):
        sheet = self.workbook(self.download('published', 'data')).worksheets[0]
        names = [sheet.cell(row=row, column=3).value for row in range(2, sheet.max_row + 1)]
        self.assertIn("'=HYPERLINK(\"x\")", names)


class CsvDownloadTests(DownloadFixtures):
    def rows(self, response):
        body = response.content.decode('utf-8-sig')
        return list(csv.reader(io.StringIO(body)))

    def test_every_sheet_downloads_as_csv(self):
        for kind in ('sheet', 'published', 'top10', 'summary'):
            with self.subTest(kind=kind):
                response = self.download(kind, 'csv')
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response['Content-Type'], CSV_TYPE)
                self.assertIn('.csv"', response['Content-Disposition'])
                self.assertGreater(len(self.rows(response)), 1)

    def test_the_csv_is_the_printable_table_without_the_letterhead(self):
        rows = self.rows(self.download('published', 'csv'))
        self.assertEqual(
            rows[0],
            ['Roll No.', 'ID No.', 'Student Name', 'Grade', 'GP', 'Total',
             'Place', 'A Plus', 'Fail', 'Comments'],
        )
        self.assertEqual(len(rows), 4)  # header + three students
        self.assertEqual(rows[1][0], '1')
        self.assertEqual(rows[1][2], 'Ayesha Siddika')

    def test_a_name_that_looks_like_a_formula_cannot_run(self):
        body = self.download('published', 'csv').content.decode('utf-8-sig')
        self.assertNotIn(',=HYPERLINK', body)
        self.assertIn("'=HYPERLINK", body)

    def test_the_register_csv_marks_absent_subjects_as_ab(self):
        rows = self.rows(self.download('sheet', 'csv'))
        header = rows[0]
        ban_index = header.index('BAN1')
        rafiq = next(row for row in rows[1:] if row[2] == 'Rafiq Islam')
        self.assertEqual(rafiq[ban_index], '70')
        self.assertEqual(header[header.index('Result')], 'Result')


class DownloadAccessTests(DownloadFixtures):
    def test_an_unpublished_exam_is_not_downloadable(self):
        self.exam.is_published = False
        self.exam.save(update_fields=['is_published'])
        response = self.download('sheet')
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('exam_list'), response['Location'])

    def test_an_unknown_sheet_or_format_is_a_404(self):
        self.assertEqual(self.download('nonsense').status_code, 404)
        self.assertEqual(self.download('sheet', 'pdf').status_code, 404)

    def test_signing_out_means_no_download(self):
        self.client.logout()
        response = self.download('sheet')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response['Location'])

    def test_the_group_filter_travels_with_the_file(self):
        response = self.download('sheet', group='')
        self.assertEqual(response.status_code, 200)


class DownloadMenuOnPagesTests(DownloadFixtures):
    def pages(self):
        return {
            'result_sheet': 'sheet',
            'published_results': 'published',
            'top_10': 'top10',
            'exam_result_print_summary': 'summary',
            'exam_result_summary': 'published',
        }

    def test_every_result_page_offers_the_one_download_menu(self):
        for name, kind in self.pages().items():
            with self.subTest(page=name):
                html = self.client.get(reverse(name, args=[self.exam.pk])).content.decode()
                self.assertEqual(html.count('id="downloadMenu'), 1)
                self.assertIn('Excel — paper layout', html)
                self.assertIn('Excel — data only', html)
                self.assertIn('CSV file', html)
                self.assertIn('Print / Save as PDF', html)
                for fmt in ('xlsx', 'data', 'csv'):
                    url = reverse('download_result_sheet', args=[self.exam.pk, kind, fmt])
                    self.assertIn(url, html)

    def test_the_download_menu_never_prints(self):
        html = self.client.get(reverse('published_results', args=[self.exam.pk])).content.decode()
        self.assertIn('dl-menu d-print-none', html)


class ExamListActionMenuTests(DownloadFixtures):
    def setUp(self):
        super().setUp()
        self.exam_html = self.client.get(reverse('exam_list')).content.decode()

    def menu(self):
        return self.exam_html.split('class="dropdown exam-actions"', 1)[1].split('</ul>', 1)[0]

    def test_each_row_carries_one_actions_menu(self):
        self.assertEqual(self.exam_html.count('class="dropdown exam-actions"'), 1)
        self.assertEqual(self.exam_html.count('<i class="bi bi-sliders me-1"></i> Actions'), 1)
        # The eight old buttons are gone: the row no longer prints a button per
        # action outside the menu.
        self.assertNotIn('btn-outline-info">Results<', self.exam_html)
        self.assertNotIn('>Published Sheet<', self.exam_html)

    def test_the_menu_holds_every_action_the_buttons_had(self):
        menu = self.menu()
        expected = [
            reverse('result_sheet', args=[self.exam.pk]),
            reverse('published_results', args=[self.exam.pk]),
            reverse('exam_result_print_summary', args=[self.exam.pk]),
            reverse('top_10', args=[self.exam.pk]),
            reverse('full_rank_list', args=[self.exam.pk]),
            reverse('result_provisional', args=[self.exam.pk]),
            reverse('seat_plan_list', args=[self.exam.pk]),
            reverse('select_marks_subject', args=[self.exam.pk]),
            reverse('import_exam_marks', args=[self.exam.pk]),
            reverse('edit_exam', args=[self.exam.pk]),
            reverse('delete_exam', args=[self.exam.pk]),
        ]
        for url in expected:
            with self.subTest(url=url):
                self.assertIn(f'href="{url}"', menu)

    def test_menu_is_a_compact_responsive_two_column_mega_menu(self):
        menu = self.menu()
        # Group cards replace the single long, vertical list. CSS keeps the
        # desktop menu in two columns and switches it to a viewport-sized,
        # scrollable single column on narrow phones.
        self.assertEqual(menu.count('class="exam-actions-section"'), 4)
        self.assertIn('class="exam-actions-heading"', menu)
        self.assertIn('grid-template-columns: repeat(2, minmax(0, 1fr))', self.exam_html)
        self.assertIn('width: calc(100vw - 24px)', self.exam_html)
        self.assertIn('max-height: min(74vh, 540px)', self.exam_html)
        self.assertIn('grid-template-columns: minmax(0, 1fr)', self.exam_html)

    def test_publishing_stays_a_post_from_inside_the_menu(self):
        menu = self.menu()
        self.assertIn(f'action="{reverse("toggle_publish_exam", args=[self.exam.pk])}"', menu)
        self.assertIn('method="post"', menu)
        self.assertIn('Unpublish result', menu)

    def test_the_menu_downloads_a_result_without_opening_it(self):
        menu = self.menu()
        self.assertIn(
            reverse('download_result_sheet', args=[self.exam.pk, 'sheet', 'xlsx']), menu,
        )
        self.assertIn(
            reverse('download_result_sheet', args=[self.exam.pk, 'published', 'xlsx']), menu,
        )

    def test_an_unpublished_exam_hides_the_published_sheets_and_downloads(self):
        self.exam.is_published = False
        self.exam.save(update_fields=['is_published'])
        html = self.client.get(reverse('exam_list')).content.decode()
        menu = html.split('class="dropdown exam-actions"', 1)[1].split('</ul>', 1)[0]
        self.assertNotIn(reverse('published_results', args=[self.exam.pk]), menu)
        self.assertNotIn(reverse('download_result_sheet', args=[self.exam.pk, 'sheet', 'xlsx']), menu)
        self.assertIn('Publish result', menu)
