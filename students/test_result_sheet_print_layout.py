"""The owner-supplied paper register is the result sheet's print contract.

These are presentation regressions only: the existing result builder remains
responsible for marks, GPA, subject choices, absence and merit positions.
"""
from html.parser import HTMLParser
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import (
    Exam, ExamMark, Institution, Student, Subject, SubjectMarkSetting,
    SubjectRequirement,
)
from .templatetags.student_filters import class_label, ordinal


class RegisterParser(HTMLParser):
    """Small, dependency-free view of the actual rendered register table."""

    def __init__(self, html):
        super().__init__()
        self.in_table = False
        self.in_head = False
        self.headers = []
        self.rows = []
        self.cell = None
        self.row = None
        self.header_rows = 0
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'table' and attrs.get('aria-label') == 'Subject-wise marks and class results':
            self.in_table = True
        if not self.in_table:
            return
        if tag == 'thead':
            self.in_head = True
        if tag == 'tr':
            if self.in_head:
                self.header_rows += 1
            else:
                self.row = []
        if tag in ('th', 'td'):
            self.cell = {'tag': tag, 'attrs': attrs, 'text': ''}

    def handle_data(self, data):
        if self.cell is not None:
            self.cell['text'] += data

    def handle_endtag(self, tag):
        if not self.in_table:
            return
        if tag in ('th', 'td') and self.cell is not None:
            self.cell['text'] = ' '.join(self.cell['text'].split())
            if tag == 'th':
                self.headers.append(self.cell)
            elif self.row is not None:
                self.row.append(self.cell)
            self.cell = None
        if tag == 'tr' and self.row is not None:
            self.rows.append(self.row)
            self.row = None
        if tag == 'thead':
            self.in_head = False
        if tag == 'table':
            self.in_table = False


class PaperRegisterLayoutTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.institution = Institution.objects.create(name='Paper Register School', classes='8')
        cls.admin = get_user_model().objects.create_superuser('paper-admin', password='password')
        cls.subjects = [
            Subject.objects.create(code=code, name=name, full_marks=100)
            for code, name in (
                ('BAN1', 'Bangla 1st Paper'), ('BAN2', 'Bangla 2nd Paper'),
                ('ENG1', 'English 1st Paper'), ('ENG2', 'English 2nd Paper'),
                ('MATH', 'General Mathematics'), ('AGRI', 'Agriculture Studies'),
                ('REL', 'Religion & Moral Education'), ('SCI', 'General Science'),
                ('BWO', 'Bangladesh & World Orientation'), ('ICT', 'Information Technology'),
            )
        ]
        for subject in cls.subjects:
            SubjectRequirement.objects.create(
                institution=cls.institution, admission_class='8', subject=subject,
                requirement_type='MANDATORY',
            )
            SubjectMarkSetting.objects.create(
                institution=cls.institution, admission_class='8', subject=subject,
                exam_type='MID_TERM_3', full_marks=40,
            )
        cls.exam = Exam.objects.create(
            name='Mid Term (3) Examination-2026', exam_type='MID_TERM_3',
            institution=cls.institution, admission_class='8', session='2026',
            is_published=True,
        )
        cls.student = Student.objects.create(
            institution=cls.institution, student_id='PAPER-001',
            name='Anwesha Chakraborty', admission_class='8', section='A',
            roll_no=59, admission_year=2026,
        )
        cls.failing = Student.objects.create(
            institution=cls.institution, student_id='PAPER-002',
            name='Fatahutul Nadia', admission_class='8', section='A',
            roll_no=49, admission_year=2026,
        )
        for subject in cls.subjects:
            ExamMark.objects.create(
                exam=cls.exam, student=cls.student, subject=subject, marks_obtained=35,
            )
            ExamMark.objects.create(
                exam=cls.exam, student=cls.failing, subject=subject, marks_obtained=13,
            )

    def setUp(self):
        self.client.force_login(self.admin)

    def get_sheet(self, **params):
        response = self.client.get(reverse('result_sheet', args=[self.exam.pk]), params)
        self.assertEqual(response.status_code, 200)
        return response, response.content.decode()

    def test_centered_school_heading_and_numeric_class_spelled_out(self):
        _response, html = self.get_sheet()
        masthead = html.split('<header class="print-masthead">', 1)[1].split('</header>', 1)[0]
        self.assertIn('<h1>Principal Kazi Faruky School</h1>', masthead)
        self.assertIn('Principal Kazi Faruky Welfare Trust', masthead)
        self.assertIn('Mid Term (3) Examination-2026', masthead)
        self.assertIn('Class: Eight', masthead)
        self.assertIn('Result Sheet', masthead)
        # A layout change must not bring back the superseded phone number.
        self.assertIn(settings.SCHOOL_INFO['school_phone'], masthead)
        self.assertIn(settings.SCHOOL_INFO['college_phone'], masthead)
        self.assertNotIn('01755881139', masthead)

    def test_one_header_row_with_the_exact_paper_column_order(self):
        response, html = self.get_sheet()
        table = RegisterParser(html)
        self.assertEqual(table.header_rows, 1)
        subject_headers = [f'{column["subject"].code}(40)' for column in response.context['columns']]
        self.assertEqual([cell['text'] for cell in table.headers], [
            'Roll', 'Name of Student', *subject_headers,
            'Total', 'GPA', 'Grade', 'F', 'S', 'A+', 'Place',
        ])
        self.assertNotIn('Subject-wise performance', html)
        self.assertNotIn('group-heading', html)
        self.assertNotIn('status-col', html)

    def test_marks_and_grades_share_one_cell_and_failed_marks_are_underlined(self):
        _response, html = self.get_sheet()
        table = RegisterParser(html)
        passing = next(row for row in table.rows if row[0]['text'] == '59')
        failing = next(row for row in table.rows if row[0]['text'] == '49')
        self.assertEqual(passing[0]['text'], '59')
        self.assertEqual(passing[1]['text'], 'Anwesha Chakraborty')
        self.assertEqual(passing[2]['text'], '35 (A+)')
        self.assertNotIn('subject-failed', passing[2]['attrs']['class'])
        self.assertEqual(failing[2]['text'], '13 (F)')
        self.assertIn('failed-mark', failing[2]['attrs']['class'])
        self.assertIn('subject-failed', failing[2]['attrs']['class'])
        self.assertEqual(passing[-7]['text'], '350')
        self.assertEqual(passing[-6]['text'], '5.00')
        self.assertEqual(passing[-5]['text'], 'A+')
        self.assertEqual(passing[-5]['attrs']['aria-label'], 'A+ — Pass')
        self.assertEqual([cell['text'] for cell in passing[-4:]], ['0', '10', '10', '1st'])
        self.assertEqual(passing[-1]['attrs']['class'], 'place-col')
        self.assertEqual(len(failing), 19)
        self.assertEqual([cell['text'] for cell in failing[-7:]], ['130', '0.00', 'F', '10', '0', '0', '—'])
        self.assertEqual(failing[-1]['text'], '—')
        self.assertNotIn('fail-star', html)

    def test_full_marks_come_from_the_exam_not_the_reference_image(self):
        SubjectMarkSetting.objects.filter(subject=self.subjects[0]).update(full_marks=50)
        _response, html = self.get_sheet()
        headers = {cell['text'].split('(')[0]: cell for cell in RegisterParser(html).headers}
        self.assertEqual(headers['BAN1']['text'], 'BAN1(50)')
        self.assertEqual(headers['BAN2']['text'], 'BAN2(40)')
        self.assertNotIn('full marks 100', html)
        self.assertEqual(headers['BAN1']['attrs']['title'], 'Bangla 1st Paper')

    def test_print_hides_screen_chrome_but_repeats_table_headers(self):
        _response, html = self.get_sheet()
        for selector in ('subject-codes', 'result-help', 'result-footer', 'print-meta'):
            block = html.split('class="' + selector, 1)[1].split('>', 1)[0]
            self.assertIn('d-print-none', block)
        self.assertNotIn('Internal grading system', html)
        self.assertNotIn('Guide Teacher', html)
        stylesheet = (Path(settings.BASE_DIR) / 'students/templates/students/result_sheet.html').read_text()
        print_css = stylesheet.split('@media print {', 1)[1]
        self.assertIn('.result-table-card thead { display: table-header-group; }', print_css)
        self.assertIn('.result-table-card tbody tr { break-inside: avoid; page-break-inside: avoid; }', print_css)
        self.assertIn('.failed-mark .mark-row, .absent-mark.subject-failed .mark-row { font-weight: 700; text-decoration: underline;', print_css)
        self.assertIn('background: #fff !important', print_css)
        self.assertNotIn('text-overflow: ellipsis', stylesheet)

    def test_full_print_keeps_the_layout_and_includes_every_student(self):
        Student.objects.bulk_create([
            Student(
                institution=self.institution, student_id=f'PAPER-BULK-{index:03}',
                name=f'Class Eight Student {index:03}', admission_class='8',
                section='A', roll_no=100 + index, admission_year=2026,
            )
            for index in range(103)
        ])
        response, html = self.get_sheet(print='1')
        self.assertEqual(len(response.context['results']), 105)
        table = RegisterParser(html)
        self.assertEqual(len(table.rows), 105)
        self.assertEqual(table.header_rows, 1)
        self.assertTrue(response.context['is_print_view'])
        self.assertNotIn('data-list-pagination', html)
        # A screen page remains bounded; only the explicit print action is full.
        response, html = self.get_sheet()
        self.assertEqual(len(response.context['results']), 100)
        self.assertEqual(len(RegisterParser(html).rows), 100)

    def test_missing_mark_keeps_AB_token_and_only_underlines_a_real_failure(self):
        ExamMark.objects.filter(student=self.student, subject=self.subjects[0]).delete()
        _response, html = self.get_sheet()
        table = RegisterParser(html)
        row = next(row for row in table.rows if row[0]['text'] == '59')
        column_index = next(i for i, header in enumerate(table.headers) if header['text'].startswith('BAN1('))
        cell = row[column_index]
        self.assertEqual(cell['text'], 'AB (F)')
        self.assertIn('absent-mark', cell['attrs']['class'])
        self.assertIn('subject-failed', cell['attrs']['class'])
        with self.settings(EXAM_ABSENT_SUBJECT_FAILS=False):
            _response, html = self.get_sheet()
            table = RegisterParser(html)
            row = next(row for row in table.rows if row[0]['text'] == '59')
            column_index = next(i for i, header in enumerate(table.headers) if header['text'].startswith('BAN1('))
            cell = row[column_index]
            self.assertEqual(cell['text'], 'AB (-)')
            self.assertNotIn('subject-failed', cell['attrs']['class'])


class PaperHeadingFilterTests(TestCase):
    def test_ordinal_suffixes_including_teens_and_large_positions(self):
        for value, expected in (
            (1, '1st'), (2, '2nd'), (3, '3rd'), (4, '4th'),
            (10, '10th'), (11, '11th'), (12, '12th'), (13, '13th'),
            (21, '21st'), (22, '22nd'), (23, '23rd'),
            (101, '101st'), (111, '111th'), (112, '112th'), (113, '113th'),
        ):
            with self.subTest(value=value):
                self.assertEqual(ordinal(value), expected)
        self.assertEqual(ordinal(None), '—')
        self.assertEqual(ordinal(''), '—')
        self.assertEqual(ordinal(0), 0)
        self.assertEqual(ordinal('unranked'), 'unranked')

    def test_class_labels_preserve_non_numeric_class_names(self):
        self.assertEqual(class_label('8'), 'Eight')
        self.assertEqual(class_label(8), 'Eight')
        self.assertEqual(class_label('12'), 'Twelve')
        self.assertEqual(class_label('Shishu'), 'Shishu')
        self.assertEqual(class_label('1st Semester'), '1st Semester')
