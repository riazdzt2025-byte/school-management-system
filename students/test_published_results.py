"""Published Results — the office's printed result sheet.

Presentation contract for the printable published-result sheet: the school
letterhead (badge, red identity lines, exam title) beside the class info box
(Year / Class / Section-Group / Pass Rate in Class / Total A Plus / Golden A
Plus), the Roll/ID/Name/Grade/GP/Total/Place/A Plus/Fail/Comments register in
roll order, the closing Section/Group summary box with the Controller of Exam /
Head Teacher signatures, and per-page footers (Guide Teacher, "Page x of y",
print date, print user, copyright). The letterhead carries the school's
*current* contact data from ``SCHOOL_INFO`` — never the retired placeholders.
"""
import re
from datetime import date
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import (
    Exam, ExamMark, Institution, InstitutionAccess, Student, StudentSubjectChoice,
    Subject, SubjectMarkSetting, SubjectRequirement,
)


def cells_of_row_containing(html, needle):
    """The stripped cell texts of the single table row containing ``needle``."""
    match = re.search(rf'<tr>(?:(?!</tr>).)*?{re.escape(needle)}(?:(?!</tr>).)*?</tr>', html, re.S)
    assert match, f'no table row contains {needle!r}'
    return [cell.strip() for cell in re.findall(r'<td[^>]*>(.*?)</td>', match.group(0), re.S)]


class PublishedResultsSheetTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.institution = Institution.objects.create(name='Published Sheet School', classes='6')
        cls.admin = get_user_model().objects.create_superuser(
            username='sheet-admin', password='password',
        )
        cls.subjects = [
            Subject.objects.create(code='PUB1', name='Bangla', full_marks=100),
            Subject.objects.create(code='PUB2', name='Mathematics', full_marks=100),
        ]
        for subject in cls.subjects:
            SubjectRequirement.objects.create(
                institution=cls.institution, admission_class='6', subject=subject,
                requirement_type='MANDATORY',
            )
            SubjectMarkSetting.objects.create(
                institution=cls.institution, admission_class='6', subject=subject,
                exam_type='MID_TERM_3', full_marks=100,
            )
        cls.exam = Exam.objects.create(
            name='Mid Term-3', exam_type='MID_TERM_3',
            institution=cls.institution, admission_class='6', section='A',
            session='2025-2026', is_published=True,
        )
        # Created out of roll order on purpose: the sheet must read down the
        # roll (1, 2, 3), never the creation order.
        cls.zara = Student.objects.create(
            institution=cls.institution, student_id='PUB002', name='Zara Akter',
            admission_class='6', section='A', roll_no=2, admission_year=2026,
        )
        cls.amit = Student.objects.create(
            institution=cls.institution, student_id='PUB001', name='Amit Roy',
            admission_class='6', section='A', roll_no=1, admission_year=2026,
        )
        cls.rahim = Student.objects.create(
            institution=cls.institution, student_id='PUB003', name='Rahim Uddin',
            admission_class='6', section='A', roll_no=3, admission_year=2026,
        )
        marks = [
            # Zara: 85 + 85 -> A+ in both papers, Golden A Plus, place 1.
            ExamMark(exam=cls.exam, student=cls.zara, subject=cls.subjects[0], marks_obtained=85),
            ExamMark(exam=cls.exam, student=cls.zara, subject=cls.subjects[1], marks_obtained=85),
            # Amit: 75 + 75 -> A (4.00), place 2.
            ExamMark(exam=cls.exam, student=cls.amit, subject=cls.subjects[0], marks_obtained=75),
            ExamMark(exam=cls.exam, student=cls.amit, subject=cls.subjects[1], marks_obtained=75),
            # Rahim: one failed paper -> whole result F, place 0.
            ExamMark(exam=cls.exam, student=cls.rahim, subject=cls.subjects[0], marks_obtained=85),
            ExamMark(exam=cls.exam, student=cls.rahim, subject=cls.subjects[1], marks_obtained=30),
        ]
        ExamMark.objects.bulk_create(marks)

    def setUp(self):
        self.client.force_login(self.admin)

    def get_sheet(self, **params):
        response = self.client.get(reverse('published_results', args=[self.exam.pk]), params)
        self.assertEqual(response.status_code, 200)
        return response, response.content.decode('utf-8')

    # ------------------------------------------------------------ access gates
    def test_unpublished_exam_redirects_to_exam_list(self):
        self.exam.is_published = False
        self.exam.save(update_fields=['is_published'])
        response = self.client.get(reverse('published_results', args=[self.exam.pk]))
        self.assertRedirects(response, reverse('exam_list'))

    def test_other_institution_exam_is_404(self):
        other = Institution.objects.create(name='Other School', classes='6')
        clerk = get_user_model().objects.create_user(username='other-clerk', password='password')
        InstitutionAccess.objects.create(user=clerk, institution=other, department='Office')
        # The clerk's access covers `other` only — this exam belongs to the
        # test institution, so the published sheet must 404 for them.
        self.client.force_login(clerk)
        response = self.client.get(reverse('published_results', args=[self.exam.pk]))
        self.assertEqual(response.status_code, 404)

    # -------------------------------------------------------------- letterhead
    def test_letterhead_carries_current_school_contact_data(self):
        _response, html = self.get_sheet()
        self.assertIn('<h1 class="pr-school">Principal Kazi Faruky School</h1>', html)
        self.assertIn('Founder: Professor Kazi Faruky Kallan Trust', html)
        self.assertIn('Mid Term-3', html)
        # Current contact data — and never the retired placeholders (the same
        # contract as the school-contact-details tests).
        self.assertIn(settings.SCHOOL_INFO['address'], html)
        self.assertIn(settings.SCHOOL_INFO['school_phone'], html)
        self.assertIn(settings.SCHOOL_INFO['college_phone'], html)
        self.assertNotIn('01850790086', html)
        self.assertNotIn('Lakshmipur-3711', html)

    def test_info_box_year_class_section_group_and_rates(self):
        _response, html = self.get_sheet()
        # Year comes from the session's ending year; Class is zero-padded and
        # spelled out; pass rate in the info box is truncated like the printout.
        self.assertIn('<td class="pr-info-label">Year</td><td>2026</td>', html)
        self.assertIn('<td class="pr-info-label">Class</td><td>06 (Six)</td>', html)
        self.assertIn('<td class="pr-info-label">Section/Group</td><td>A</td>', html)
        self.assertIn('<td class="pr-info-label">Pass Rate in Class</td><td>66 %</td>', html)
        self.assertIn('<td class="pr-info-label">Total A Plus</td><td>1</td>', html)
        self.assertIn('<td class="pr-info-label">Golden A Plus</td><td>1</td>', html)

    def test_exam_date_year_beats_session_year(self):
        self.exam.exam_date = date(2025, 3, 1)
        self.exam.save(update_fields=['exam_date'])
        _response, html = self.get_sheet()
        self.assertIn('<td class="pr-info-label">Year</td><td>2025</td>', html)

    # ----------------------------------------------------------- register table
    def test_exact_column_order(self):
        _response, html = self.get_sheet()
        self.assertEqual(
            re.findall(r'<th>([^<]*)</th>', html),
            ['Roll No.', 'ID No.', 'Student Name', 'Grade', 'GP', 'Total',
             'Place', 'A Plus', 'Fail', 'Comments'],
        )

    def test_rows_follow_roll_order(self):
        _response, html = self.get_sheet()
        self.assertLess(html.index('PUB001'), html.index('PUB002'))
        self.assertLess(html.index('PUB002'), html.index('PUB003'))

    def test_passing_row_cells(self):
        _response, html = self.get_sheet()
        self.assertEqual(
            cells_of_row_containing(html, 'PUB001'),
            ['1', 'PUB001', 'Amit Roy', 'A', '4.00', '150', '2', '0', '0', ''],
        )

    def test_failing_row_shows_zero_place_and_fail_counts(self):
        _response, html = self.get_sheet()
        self.assertEqual(
            cells_of_row_containing(html, 'PUB003'),
            ['3', 'PUB003', 'Rahim Uddin', 'F', '0.00', '115', '0', '1', '1', ''],
        )

    def test_top_row_shows_place_and_a_plus_count(self):
        _response, html = self.get_sheet()
        self.assertEqual(
            cells_of_row_containing(html, 'PUB002'),
            ['2', 'PUB002', 'Zara Akter', 'A+', '5.00', '170', '1', '2', '0', ''],
        )

    # ------------------------------------------------------- closing summary box
    def test_closing_summary_box_and_signatures(self):
        _response, html = self.get_sheet()
        self.assertIn('<td class="pr-info-label">Total Student</td><td>3</td>', html)
        self.assertIn('<td class="pr-info-label">Total Pass</td><td>2</td>', html)
        self.assertIn('<td class="pr-info-label">Total Fail</td><td>1</td>', html)
        self.assertIn('<td class="pr-info-label">Pass Rate</td><td>66.67 %</td>', html)
        self.assertIn('Controller of Exam', html)
        self.assertIn('Head Teacher', html)

    # --------------------------------------------------- footers and pagination
    def test_footer_print_date_user_and_copyright(self):
        _response, html = self.get_sheet()
        self.assertIn('Guide Teacher</div>', html)
        self.assertIn('Print Date:', html)
        self.assertIn('Print User: sheet-admin', html)
        self.assertRegex(html, r'Copyright (?:©|&copy;)')
        self.assertIn(settings.COPYRIGHT_HOLDER, html)
        self.assertIn(f'Software by: {settings.DEVELOPER_NAME}', html)

    @mock.patch('students.views.PUBLISHED_RESULTS_ROWS_PER_PAGE', 2)
    def test_every_page_repeats_letterhead_and_footer_with_page_numbers(self):
        _response, html = self.get_sheet()
        # 3 students at 2 rows per page -> 2 sheets: "Page 1 of 2" / "Page 2 of 2".
        self.assertIn('Page 1 of 2', html)
        self.assertIn('Page 2 of 2', html)
        self.assertEqual(html.count('Principal Kazi Faruky School</h1>'), 2)
        self.assertEqual(html.count('</div>Guide Teacher</div>'), 2)
        self.assertEqual(html.count('<th>Roll No.</th>'), 2)
        # The closing summary/signatures belong on the last sheet only.
        self.assertEqual(html.count('Total Student</td>'), 1)
        self.assertEqual(html.count('Controller of Exam'), 1)

    @mock.patch('students.views.PUBLISHED_RESULTS_ROWS_PER_PAGE', 2)
    def test_rows_split_across_sheets_in_roll_order(self):
        _response, html = self.get_sheet()
        first, second = html.split('Page 1 of 2', 1)
        self.assertIn('PUB001', first)
        self.assertIn('PUB002', first)
        self.assertNotIn('PUB003', first)
        self.assertIn('PUB003', second)

    def test_group_picker_off_for_fixed_section_exam(self):
        response, html = self.get_sheet()
        self.assertFalse(response.context['show_group_picker'])
        self.assertNotIn('id="pr-group-select"', html)


class PublishedResultsGoldenAPlusTests(TestCase):
    """Total A Plus counts GPA-5.00 students; Golden A Plus needs A+ everywhere."""

    @classmethod
    def setUpTestData(cls):
        cls.institution = Institution.objects.create(name='Golden A Plus School', classes='9')
        cls.admin = get_user_model().objects.create_superuser(
            username='golden-admin', password='password',
        )
        cls.main_subjects = [
            Subject.objects.create(code='GMAIN1', name='Main One', full_marks=100),
            Subject.objects.create(code='GMAIN2', name='Main Two', full_marks=100),
        ]
        cls.fourth = Subject.objects.create(
            code='GFOUR', name='Fourth Paper', full_marks=100, category='FOURTH',
        )
        for subject in cls.main_subjects:
            SubjectRequirement.objects.create(
                institution=cls.institution, admission_class='9', subject=subject,
                requirement_type='MANDATORY',
            )
        cls.fourth_requirement = SubjectRequirement.objects.create(
            institution=cls.institution, admission_class='9', subject=cls.fourth,
            requirement_type='OPTIONAL', optional_set_key='fourth-choice',
        )
        for subject in [*cls.main_subjects, cls.fourth]:
            SubjectMarkSetting.objects.create(
                institution=cls.institution, admission_class='9', subject=subject,
                exam_type='MID_TERM_3', full_marks=100,
            )
        cls.exam = Exam.objects.create(
            name='Mid Term-3', exam_type='MID_TERM_3', institution=cls.institution,
            admission_class='9', session='2025-2026', is_published=True,
        )
        cls.golden = Student.objects.create(
            institution=cls.institution, student_id='G001', name='Golden Kid',
            admission_class='9', roll_no=1, admission_year=2026,
        )
        cls.capped = Student.objects.create(
            institution=cls.institution, student_id='G002', name='Capped Kid',
            admission_class='9', roll_no=2, admission_year=2026,
        )
        for student in (cls.golden, cls.capped):
            StudentSubjectChoice.objects.create(student=student, requirement=cls.fourth_requirement)
        ExamMark.objects.bulk_create([
            # Golden: A+ (85) in every paper including the fourth.
            ExamMark(exam=cls.exam, student=cls.golden, subject=cls.main_subjects[0], marks_obtained=85),
            ExamMark(exam=cls.exam, student=cls.golden, subject=cls.main_subjects[1], marks_obtained=85),
            ExamMark(exam=cls.exam, student=cls.golden, subject=cls.fourth, marks_obtained=85),
            # Capped: A+ mains and an A fourth (75). The fourth-subject bonus
            # still caps the GPA at 5.00 -> Total A Plus but not Golden.
            ExamMark(exam=cls.exam, student=cls.capped, subject=cls.main_subjects[0], marks_obtained=85),
            ExamMark(exam=cls.exam, student=cls.capped, subject=cls.main_subjects[1], marks_obtained=85),
            ExamMark(exam=cls.exam, student=cls.capped, subject=cls.fourth, marks_obtained=75),
        ])

    def test_total_a_plus_counts_both_but_golden_only_all_a_plus(self):
        self.client.force_login(self.admin)
        html = self.client.get(reverse('published_results', args=[self.exam.pk])).content.decode('utf-8')
        self.assertIn('<td class="pr-info-label">Total A Plus</td><td>2</td>', html)
        self.assertIn('<td class="pr-info-label">Golden A Plus</td><td>1</td>', html)
        # The capped student is still published as A+ / 5.00 overall.
        self.assertEqual(
            cells_of_row_containing(html, 'G002'),
            ['2', 'G002', 'Capped Kid', 'A+', '5.00', '245', '2', '2', '0', ''],
        )
