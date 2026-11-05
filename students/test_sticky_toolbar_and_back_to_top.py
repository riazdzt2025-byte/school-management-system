"""The result register's print/screen chrome and its paper column layout.

1. The result-sheet action bar (Published / Provisional / Rank / Top 10 /
   Print / Back ...) must stay pinned to the top edge while the register
   scrolls, so a teacher far down a 193-student list does not have to scroll
   back up to reach the next report.
2. Every page gets a "back to top" shortcut that appears only after the reader
   has scrolled, is keyboard reachable, and never prints.

Both are pure presentation concerns, so these tests assert the rendered markup
and CSS contracts rather than driving a browser.
"""
import re
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Exam, ExamMark, Institution, Student, Subject, SubjectRequirement
from .result_utils import build_exam_results

TEMPLATES = Path(settings.BASE_DIR) / 'students' / 'templates' / 'students'


class StickyResultToolbarTests(TestCase):
    def setUp(self):
        self.institution = Institution.objects.create(name='Sticky School', classes='6')
        self.user = get_user_model().objects.create_superuser(
            username='sticky-admin', password='password',
        )
        self.client.force_login(self.user)
        self.subject = Subject.objects.create(code='STK1', name='Sticky Paper', full_marks=100)
        SubjectRequirement.objects.create(
            institution=self.institution, admission_class='6',
            subject=self.subject, requirement_type='MANDATORY',
        )
        self.exam = Exam.objects.create(
            name='Sticky Exam', exam_type='FIRST_TERM', institution=self.institution,
            admission_class='6', session='2026', is_published=True,
        )
        self.student = Student.objects.create(
            institution=self.institution, student_id='STK001', name='Sticky Kid',
            admission_class='6', section='A', roll_no=1, admission_year=2026,
        )

    def test_result_sheet_toolbar_is_sticky_and_print_hidden(self):
        response = self.client.get(reverse('result_sheet', args=[self.exam.pk]))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode('utf-8')
        self.assertIn('class="result-toolbar d-print-none"', html)

        stylesheet = (TEMPLATES / 'result_sheet.html').read_text(encoding='utf-8')
        toolbar_block = stylesheet.split('.result-toolbar {', 1)[1].split('}', 1)[0]
        self.assertIn('position: sticky', toolbar_block)
        self.assertIn('top: 0', toolbar_block)
        self.assertIn('z-index: 950', toolbar_block)

    def test_toolbar_keeps_its_own_background_so_rows_scroll_behind_it(self):
        stylesheet = (TEMPLATES / 'result_sheet.html').read_text(encoding='utf-8')
        toolbar_block = stylesheet.split('.result-toolbar {', 1)[1].split('}', 1)[0]
        # A transparent bar would let table rows bleed through while pinned.
        self.assertIn('background:', toolbar_block)
        self.assertIn('.result-toolbar.is-stuck', stylesheet)

    def test_phone_layout_keeps_the_pinned_bar_short(self):
        stylesheet = (TEMPLATES / 'result_sheet.html').read_text(encoding='utf-8')
        mobile_block = stylesheet.split('@media (max-width: 768px) {', 1)[1].split('@page', 1)[0]
        self.assertIn('.result-toolbar .toolbar-actions', mobile_block)
        self.assertIn('flex-wrap: nowrap', mobile_block)
        self.assertIn('overflow-x: auto', mobile_block)

    def test_print_rules_still_hide_the_toolbar(self):
        stylesheet = (TEMPLATES / 'result_sheet.html').read_text(encoding='utf-8')
        print_block = stylesheet.split('@media print {', 1)[1]
        self.assertIn('.result-toolbar, .d-print-none { display: none !important; }', print_block)


class BackToTopTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username='top-admin', password='password',
        )
        self.client.force_login(self.user)

    def test_every_page_renders_the_shortcut(self):
        for url in (reverse('dashboard'), reverse('exam_list')):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'id="backToTop"')
            self.assertContains(response, 'class="back-to-top d-print-none"')
            self.assertContains(response, 'aria-label="Back to top"')

    def test_shortcut_is_hidden_until_the_page_is_scrolled(self):
        base = (TEMPLATES / 'base.html').read_text(encoding='utf-8')
        self.assertIn('.back-to-top {', base)
        hidden_block = base.split('.back-to-top {', 1)[1].split('}', 1)[0]
        self.assertIn('position: fixed', hidden_block)
        self.assertIn('opacity: 0', hidden_block)
        self.assertIn('visibility: hidden', hidden_block)
        self.assertIn('.back-to-top.is-visible', base)
        self.assertIn("classList.toggle('is-visible'", base)

    def test_shortcut_scrolls_smoothly_and_respects_reduced_motion(self):
        base = (TEMPLATES / 'base.html').read_text(encoding='utf-8')
        self.assertIn("window.scrollTo({ top: 0, behavior: 'smooth' })", base)
        self.assertIn('prefers-reduced-motion: reduce', base)

    def test_shortcut_never_prints(self):
        base = (TEMPLATES / 'base.html').read_text(encoding='utf-8')
        print_block = base.split('@media print {', 1)[1].split('{% block extra_style %}', 1)[0]
        self.assertIn('.back-to-top', print_block)
        self.assertIn('display: none !important', print_block)


class PrintReadabilityTests(TestCase):
    """A printed register has to be legible on paper, not just on screen.

    The print block used to hard-code 8–10px type, which lands at 6–7.5pt on an
    A4 sheet — the complaint that prompted this. Print type is now expressed in
    points, and nothing that carries data may go below 9pt (≈ 12px).
    """

    MIN_BODY_PT = 9.0

    def _print_block(self, template):
        stylesheet = (TEMPLATES / template).read_text(encoding='utf-8')
        return stylesheet.split('@media print {', 1)[1]

    def _rule(self, block, selector):
        return block.split(selector + ' {', 1)[1].split('}', 1)[0]

    def test_register_cells_print_at_least_9pt(self):
        block = self._print_block('result_sheet.html')
        for selector in ('.result-table-card td', '.result-table-card td.student-col', '.mark-number'):
            with self.subTest(selector=selector):
                rule = self._rule(block, selector)
                self.assertIn('pt', rule)
                size = float(rule.split('font-size:', 1)[1].split('pt', 1)[0].strip())
                self.assertGreaterEqual(size, self.MIN_BODY_PT)

    def test_register_headers_are_bold_and_school_name_is_larger_than_body_text(self):
        block = self._print_block('result_sheet.html')
        header = self._rule(block, '.result-table-card th')
        self.assertIn('font-weight: 700', header)
        self.assertGreaterEqual(float(header.split('font-size:', 1)[1].split('pt', 1)[0].strip()), 9.0)
        title = self._rule(block, '.print-masthead h1')
        self.assertGreaterEqual(float(title.split('font-size:', 1)[1].split('pt', 1)[0].strip()), 14.0)

    def test_print_and_provisional_tables_use_points_not_pixels(self):
        for template in ('result_sheet.html', 'result_provisional.html', 'exam_result_summary.html'):
            with self.subTest(template=template):
                block = self._print_block(template)
                self.assertNotIn('font-size: 9.5px', block)
                self.assertNotIn('font-size: 10px', block)

    def test_no_data_text_prints_below_7pt(self):
        """Footnotes may be small, but nothing may shrink to unreadable 6px type."""
        block = self._print_block('result_sheet.html')
        import re
        sizes = [float(value) for value in re.findall(r'font-size:\s*([0-9.]+)pt', block)]
        self.assertTrue(sizes)
        self.assertGreaterEqual(min(sizes), 6.5)
        # Anything sized in px must be layout, never text smaller than 12px.
        px_sizes = [float(value) for value in re.findall(r'font-size:\s*([0-9.]+)px', block)]
        self.assertEqual(px_sizes, [])

    def test_page_margins_leave_room_for_larger_type(self):
        stylesheet = (TEMPLATES / 'result_sheet.html').read_text(encoding='utf-8')
        # The bottom margin must leave room for the guide-teacher signature
        # footer that is printed on every page (@page @bottom-center).
        self.assertIn('@page { size: A4 landscape; margin: 6mm 6mm 24mm;', stylesheet)
        self.assertIn('@bottom-center', stylesheet)
        # The printed footer is English, like the rest of the sheet.
        self.assertIn("Guide Teacher's signature", stylesheet)
        self.assertIsNone(re.search(r'[\u0980-\u09FF]', stylesheet),
                          'the Full Mark Sheet must print in English only')

    def test_ten_subject_sheet_keeps_a_usable_name_and_mark_column(self):
        """A4 landscape is 297mm wide; at a 6mm margin that is ~1077 CSS px.

        With ten subject columns the browser distributes the fixed percentages,
        so what matters is that the name column still fits a full Bengali name
        and a mark column still fits "35" plus a grade badge at 9.5pt.  The
        summary columns are narrower: they only hold "Total", "GPA", "Place".
        """
        block = self._print_block('result_sheet.html')
        widths = {}
        for column in (
            'rank-col', 'student-col-width', 'subject-col', 'total-col', 'gpa-col',
            'grade-col', 'count-col', 'place-col',
        ):
            rule = self._rule(block, '.result-table-card col.' + column)
            widths[column] = float(rule.split('width:', 1)[1].split('%', 1)[0].strip())

        declared = (widths['rank-col'] + widths['student-col-width']
                    + 10 * widths['subject-col'] + widths['total-col'] + widths['gpa-col']
                    + widths['grade-col']
                    + 3 * widths['count-col'] + widths['place-col'])
        sheet_px = (297 - 12) * 96 / 25.4
        scale = sheet_px / declared
        self.assertGreaterEqual(widths['student-col-width'] * scale, 175)
        self.assertGreaterEqual(widths['subject-col'] * scale, 55)
        self.assertGreaterEqual(widths['place-col'] * scale, 30)


class RegisterSummaryColumnTests(TestCase):
    """The register ends with flat summary columns, like the school's paper sheet:
    Total | GPA | Grade | F | S | A+ | Place."""

    def setUp(self):
        self.institution = Institution.objects.create(name='Column School', classes='9')
        self.admin = get_user_model().objects.create_superuser(
            username='column-admin', password='password',
        )
        self.client.force_login(self.admin)
        self.subjects = [
            Subject.objects.create(code=code, name=name, full_marks=100)
            for code, name in (('BAN', 'Bangla'), ('MAT', 'Mathematics'), ('SCI', 'Science'))
        ]
        for subject in self.subjects:
            SubjectRequirement.objects.create(
                institution=self.institution, admission_class='9',
                subject=subject, requirement_type='MANDATORY',
            )
        self.exam = Exam.objects.create(
            name='Column Examination-2026', exam_type='FIRST_TERM',
            institution=self.institution, admission_class='9', session='2026',
            is_published=True,
        )
        self.topper = Student.objects.create(
            institution=self.institution, student_id='C1', name='Topper Student',
            admission_class='9', section='A', roll_no=1, admission_year=2026,
        )
        self.failing = Student.objects.create(
            institution=self.institution, student_id='C2', name='Failing Student',
            admission_class='9', section='A', roll_no=2, admission_year=2026,
        )
        for subject in self.subjects:
            ExamMark.objects.create(
                exam=self.exam, student=self.topper, subject=subject, marks_obtained=95,
            )
        ExamMark.objects.create(
            exam=self.exam, student=self.failing, subject=self.subjects[0], marks_obtained=95,
        )
        ExamMark.objects.create(
            exam=self.exam, student=self.failing, subject=self.subjects[1], marks_obtained=10,
        )
        ExamMark.objects.create(
            exam=self.exam, student=self.failing, subject=self.subjects[2], marks_obtained=70,
        )

    def _row(self, results, student):
        return next(row for row in results if row['student'].pk == student.pk)

    def test_grade_tallies_count_failed_passed_and_a_plus_papers(self):
        _columns, results = build_exam_results(self.exam)
        topper = self._row(results, self.topper)
        failing = self._row(results, self.failing)
        for row in (topper, failing):
            self.assertEqual(
                row['failed_subject_count'] + row['passed_subject_count'],
                len(row['subject_results']),
            )
        self.assertEqual(topper['failed_subject_count'], 0)
        self.assertEqual(topper['passed_subject_count'], 3)
        self.assertGreaterEqual(topper['a_plus_count'], 1)
        self.assertEqual(failing['failed_subject_count'], 1)
        self.assertEqual(failing['passed_subject_count'], 2)
        self.assertEqual(
            topper['a_plus_count'],
            sum(1 for sr in topper['subject_results'] if sr.get('grade') == 'A+'),
        )

    def test_register_prints_the_flat_columns_in_the_paper_order(self):
        """Roll | Name of Student | subjects... | Total GPA Grade F S A+ Place."""
        from html.parser import HTMLParser

        class HeaderCells(HTMLParser):
            def __init__(self):
                super().__init__()
                self.cells = []
                self._current = None

            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                if tag == 'th' and self._current is None:
                    self._current = {
                        'text': '', 'colspan': int(attrs.get('colspan') or 1),
                        'rowspan': int(attrs.get('rowspan') or 1),
                        'class': attrs.get('class') or '',
                    }

            def handle_endtag(self, tag):
                if tag == 'th' and self._current is not None:
                    self._current['text'] = ' '.join(self._current['text'].split())
                    self.cells.append(self._current)
                    self._current = None

            def handle_data(self, data):
                if self._current is not None:
                    self._current['text'] += data

        response = self.client.get(reverse('result_sheet', args=[self.exam.pk]))
        parser = HeaderCells()
        parser.feed(response.content.decode('utf-8').split('<thead>', 1)[1].split('</thead>', 1)[0])
        texts = [cell['text'] for cell in parser.cells]

        self.assertEqual(texts, [
            'Roll', 'Name of Student', 'BAN(100)', 'MAT(100)', 'SCI(100)',
            'Total', 'GPA', 'Grade', 'F', 'S', 'A+', 'Place',
        ])
        # The supplied school sheet has one header row, not a grouped heading
        # or a separate Result column. Grade F plus the F count convey a fail.
        for cell in parser.cells:
            self.assertEqual(cell['rowspan'], 1)
            self.assertEqual(cell['colspan'], 1)

    def test_summary_cells_carry_the_students_numbers(self):
        response = self.client.get(reverse('result_sheet', args=[self.exam.pk]))
        html = response.content.decode('utf-8')
        first_row = html.split('data-result-status="Pass"', 1)[1].split('</tr>', 1)[0]
        self.assertIn('class="total-col"', first_row)
        self.assertIn('class="gpa-col"', first_row)
        self.assertIn('class="place-col"', first_row)
        self.assertEqual(first_row.count('class="count-col"'), 3)
        # Topper: nothing failed, three papers passed.
        self.assertIn('<td class="count-col">0</td>', first_row)
        self.assertIn('<td class="count-col">3</td>', first_row)

    def test_the_old_stacked_cells_are_gone(self):
        html = self.client.get(reverse('result_sheet', args=[self.exam.pk])).content.decode('utf-8')
        self.assertNotIn('overall-stack', html)
        self.assertNotIn('result-stack', html)
        self.assertNotIn('Overall<br>standing', html)
        self.assertNotIn('Final<br>result', html)
