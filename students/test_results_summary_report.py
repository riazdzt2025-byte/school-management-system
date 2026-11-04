"""Results Summary — the section and subject-wise grade report.

One A4 portrait sheet in the same language as the other result printouts
(shared letterhead, class info box, signatures, page footer) carrying:

* **Total Grade Count in the Class** (Golden A Plus counted separately);
* **Internal Grading System** — the marks bands the exam is graded with;
* **grade × subject matrix** with per-grade and per-subject totals;
* **Grade Summary in the Section** beside the Principal / Controller of Exam
  overlines.

The page is the replacement for the old Bengali "brief + subject-wise" sheet,
so it must print in English only.
"""
import re

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Exam, ExamMark, Institution, InstitutionAccess, Student, Subject, SubjectRequirement


class ResultsSummaryReportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.institution = Institution.objects.create(name='Summary Report School', classes='6')
        cls.user = get_user_model().objects.create_superuser('rsm-admin', 'r@example.com', 'password')
        cls.subjects = [
            Subject.objects.create(code='BNG1', name='Bangla', full_marks=100),
            Subject.objects.create(code='ENG1', name='English', full_marks=100),
        ]
        for subject in cls.subjects:
            SubjectRequirement.objects.create(
                institution=cls.institution, admission_class='6', subject=subject,
                requirement_type='MANDATORY',
            )
        cls.exam = Exam.objects.create(
            name='Pre-Test Exam', exam_type='MID_TERM_3', institution=cls.institution,
            admission_class='6', section='A', session='2025-2026', is_published=True,
        )
        # Three students: one Golden (90/90), one A overall (75/75),
        # one failing overall (80/30).
        cls.golden = Student.objects.create(
            institution=cls.institution, student_id='RS001', name='Golden Kid',
            admission_class='6', section='A', roll_no=1, admission_year=2026,
        )
        cls.middle = Student.objects.create(
            institution=cls.institution, student_id='RS002', name='Middle Kid',
            admission_class='6', section='A', roll_no=2, admission_year=2026,
        )
        cls.failing = Student.objects.create(
            institution=cls.institution, student_id='RS003', name='Failing Kid',
            admission_class='6', section='A', roll_no=3, admission_year=2026,
        )
        ExamMark.objects.bulk_create([
            ExamMark(exam=cls.exam, student=cls.golden, subject=cls.subjects[0], marks_obtained=90),
            ExamMark(exam=cls.exam, student=cls.golden, subject=cls.subjects[1], marks_obtained=90),
            ExamMark(exam=cls.exam, student=cls.middle, subject=cls.subjects[0], marks_obtained=75),
            ExamMark(exam=cls.exam, student=cls.middle, subject=cls.subjects[1], marks_obtained=75),
            ExamMark(exam=cls.exam, student=cls.failing, subject=cls.subjects[0], marks_obtained=80),
            ExamMark(exam=cls.exam, student=cls.failing, subject=cls.subjects[1], marks_obtained=30),
        ])

    def setUp(self):
        self.client.force_login(self.user)

    def get_report(self, **params):
        response = self.client.get(
            reverse('exam_result_print_summary', args=[self.exam.pk]), params,
        )
        self.assertEqual(response.status_code, 200)
        return response, response.content.decode('utf-8')

    # ------------------------------------------------------------- sheet frame
    def test_uses_the_shared_portrait_letterhead(self):
        _response, html = self.get_report()
        self.assertIn('@page { size: A4 portrait', html)
        self.assertIn('<h1 class="pr-school">Principal Kazi Faruky School</h1>', html)
        self.assertIn('<td class="pr-info-label">Year</td><td>2026</td>', html)
        self.assertIn('<td class="pr-info-label">Class</td><td>06 (Six)</td>', html)
        self.assertIn('<td class="pr-info-label">Section/Group</td><td>A</td>', html)
        self.assertIn('Section and Subject-wise Summary', html)

    def test_page_is_entirely_in_english(self):
        """The old brief/subject-wise sheet was Bengali; nothing may remain."""
        _response, html = self.get_report()
        self.assertIsNone(
            re.search(r'[\u0980-\u09FF]', html),
            'the Results Summary sheet must not contain Bengali text',
        )
        self.assertIn('Total Grade Count in the Class', html)
        self.assertIn('Internal Grading System', html)
        self.assertIn('Grade Summary in the Section', html)

    def test_signatures_and_footer(self):
        _response, html = self.get_report()
        self.assertIn('Principal', html)
        self.assertIn('Controller of Exam', html)
        self.assertIn('Guide Teacher', html)
        self.assertIn('Page 1 of 1', html)
        self.assertIn('Print User: rsm-admin', html)
        self.assertIn('Print Date:', html)

    # --------------------------------------------------- total grade count box
    def test_class_grade_counts(self):
        _response, html = self.get_report()
        self.assertEqual(
            re.findall(r'<tr><td>(?:<strong>)?([^<]+)(?:</strong>)?</td><td class="rsm-num">(?:<strong>)?(\d+)',
                       html),
            [
                ('Golden A Plus', '1'),
                ('A Plus (A+)', '1'),
                ('A Regular (A)', '1'),
                ('A Minus (A-)', '0'),
                ('B Regular (B)', '0'),
                ('C Regular (C)', '0'),
                ('D Regular (D)', '0'),
                ('Fail (F)', '1'),
                ('Total Examinee', '3'),
            ],
        )

    def test_internal_grading_system_prints_the_app_scale(self):
        _response, html = self.get_report()
        for band, grade, point in (
            ('80-100', 'A+', '5.00'),
            ('70-79', 'A', '4.00'),
            ('60-69', 'A-', '3.50'),
            ('50-59', 'B', '3.00'),
            ('40-49', 'C', '2.00'),
            ('33-39', 'D', '1.00'),
            ('00-32', 'F', '0.00'),
        ):
            with self.subTest(grade=grade):
                self.assertIn(f'<tr><td>{band}</td><td>{grade}</td><td>{point}</td></tr>', html)

    # ------------------------------------------------------- grade × subject
    def test_matrix_headers_carry_code_and_full_marks(self):
        _response, html = self.get_report()
        matrix = html.split('<table class="pr-table rsm-matrix">', 1)[1]
        head = matrix.split('<thead>', 1)[1].split('</thead>', 1)[0]
        headers = re.findall(r'<th>(.*?)</th>', head, re.S)
        self.assertEqual([re.sub(r'<[^>]+>', ' ', cell).split()[0] for cell in headers],
                         ['Grade', 'BNG1', 'ENG1', 'Total'])
        self.assertIn('(100)', headers[1])

    def test_matrix_counts_per_subject_and_totals(self):
        response, _html = self.get_report()
        report = response.context['grade_report']
        counts = {row['grade']: (row['counts'], row['total']) for row in report['matrix']}
        # Bangla: 90 → A+, 80 → A+, 75 → A   ⇒ A+ 2, A 1
        # English: 90 → A+, 75 → A, 30 → F   ⇒ A+ 1, A 1, F 1
        self.assertEqual(counts['A+'], ([2, 1], 3))
        self.assertEqual(counts['A'], ([1, 1], 2))
        self.assertEqual(counts['F'], ([0, 1], 1))
        self.assertEqual(report['column_totals'], [3, 3])
        self.assertEqual(report['matrix_total'], 6)

    def test_section_summary_matches_the_class_box(self):
        response, _html = self.get_report()
        report = response.context['grade_report']
        self.assertEqual(report['section_rows'], report['class_rows'])
        self.assertEqual(report['total_students'], 3)

    # ------------------------------------------------------------- access gate
    def test_unpublished_exam_redirects(self):
        self.exam.is_published = False
        self.exam.save(update_fields=['is_published'])
        response = self.client.get(reverse('exam_result_print_summary', args=[self.exam.pk]))
        self.assertRedirects(response, reverse('exam_list'))

    def test_other_institution_exam_is_404(self):
        other = Institution.objects.create(name='Elsewhere', classes='6')
        foreign = Exam.objects.create(
            name='Foreign', exam_type='MID_TERM_3', institution=other,
            admission_class='6', session='2026', is_published=True,
        )
        clerk = get_user_model().objects.create_user(username='rsm-clerk', password='password')
        InstitutionAccess.objects.create(
            user=clerk, institution=self.institution, department='Office',
        )
        self.client.force_login(clerk)
        response = self.client.get(reverse('exam_result_print_summary', args=[foreign.pk]))
        self.assertEqual(response.status_code, 404)

    def test_result_sheet_links_to_the_summary_in_english(self):
        html = self.client.get(reverse('result_sheet', args=[self.exam.pk])).content.decode()
        self.assertIn(f'href="{reverse("exam_result_print_summary", args=[self.exam.pk])}"', html)
        self.assertIn('Results Summary</a>', html)
