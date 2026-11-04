"""Shared report chrome: logo, signatures, and the school/college name split.

Every printed document of the school carries the school badge, and the school's
signatures sit in one row at the foot of the sheet with **Guide Teacher on the
left**. A school document never prints the combined organisation name
("… School And College"): school papers show the school name only, and the
college keeps its separate name.
"""
import re

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import (
    Certificate, Exam, ExamMark, Institution, Student, Subject, SubjectRequirement,
)


def _paper(html):
    """The printed paper of a report page, without the app chrome.

    The sidebar and the on-screen school header are ``d-print-none`` chrome and
    are deliberately out of scope for "what the paper says".
    """
    for marker in ('<div class="pr-page', '<div class="result-paper">',
                   '<section class="pr-sheet"', '<div class="card-print"', '<main class="sheet">'):
        if marker in html:
            return html.split(marker, 1)[1]
    return html


def _field(html, label):
    match = re.search(r'<td class="pr-info-label">' + label + r'</td><td>([^<]*)</td>', html)
    return match.group(1) if match else None


class SchoolOnlyNameFilterTests(TestCase):
    def test_school_and_college_names_are_kept_apart(self):
        from .templatetags.student_filters import college_only, school_only

        combined = 'Principal Kazi Faruky School And College'
        self.assertEqual(school_only(combined), 'Principal Kazi Faruky School')
        self.assertEqual(college_only(combined), 'Principal Kazi Faruky College')
        self.assertEqual(school_only('ABC & College'), 'ABC')
        self.assertEqual(college_only('ABC & College'), 'ABC College')
        # Nothing to split: the name passes through untouched.
        self.assertEqual(school_only('Plain School'), 'Plain School')
        self.assertEqual(college_only('Plain School'), 'Plain School')
        self.assertEqual(school_only(None), '')


class ResultSheetChromeTests(TestCase):
    """Logo, bottom signature row and school-only names on the result sheets."""

    @classmethod
    def setUpTestData(cls):
        cls.institution = Institution.objects.create(
            name='Principal Kazi Faruky School And College', classes='6',
        )
        cls.user = get_user_model().objects.create_superuser('chrome-admin', 'c@example.com', 'password')
        cls.subject = Subject.objects.create(code='CHR1', name='Bangla', full_marks=100)
        SubjectRequirement.objects.create(
            institution=cls.institution, admission_class='6', subject=cls.subject,
            requirement_type='MANDATORY',
        )
        cls.exam = Exam.objects.create(
            name='Mid Term-3', exam_type='MID_TERM_3', institution=cls.institution,
            admission_class='6', section='A', session='2025-2026', is_published=True,
        )
        cls.student = Student.objects.create(
            institution=cls.institution, student_id='CH001', name='Chrome Student',
            admission_class='6', section='A', roll_no=1, admission_year=2026,
        )
        ExamMark.objects.create(
            exam=cls.exam, student=cls.student, subject=cls.subject, marks_obtained=85,
        )

    def setUp(self):
        self.client.force_login(self.user)

    def pages(self):
        return {
            'result_sheet': reverse('result_sheet', args=[self.exam.pk]),
            'published_results': reverse('published_results', args=[self.exam.pk]),
            'exam_result_summary': reverse('exam_result_summary', args=[self.exam.pk]),
            'top_10': reverse('top_10', args=[self.exam.pk]),
            'exam_result_print_summary': reverse('exam_result_print_summary', args=[self.exam.pk]),
            'result_card': reverse('result_card', args=[self.exam.pk, self.student.pk]),
        }

    def test_every_result_document_prints_the_logo(self):
        for name, url in self.pages().items():
            with self.subTest(page=name):
                html = self.client.get(url).content.decode()
                self.assertIn('school_logo.png', html)
                self.assertIn('<img', html)

    def test_no_result_document_prints_the_combined_name(self):
        """The printed paper never carries "… School And College".

        App chrome (sidebar, on-screen header, <title>) is out of scope: it is
        not part of the paper, and ``.school-header`` is d-print-none anyway.
        """
        for name, url in self.pages().items():
            with self.subTest(page=name):
                html = self.client.get(url).content.decode()
                self.assertNotIn('School And College', _paper(html))

    def test_signatures_sit_at_the_foot_with_guide_teacher_on_the_left(self):
        for name in ('published_results', 'top_10', 'exam_result_print_summary'):
            with self.subTest(page=name):
                html = self.client.get(self.pages()[name]).content.decode()
                row = html.split('<div class="pr-sign-row">', 1)[1].split('</div>\n\n', 1)[0]
                # Guide Teacher is the first (left-most) signature in the row,
                # the others follow on the right.
                self.assertLess(row.index('Guide Teacher'), row.index('Controller of Exam'))

    def test_full_mark_sheet_prints_in_english_only(self):
        """The landscape Full Mark Sheet was the last Bengali document."""
        html = self.client.get(self.pages()['result_sheet']).content.decode()
        self.assertIsNone(
            re.search(r'[\u0980-\u09FF]', html),
            'the Full Mark Sheet must print in English only',
        )
        self.assertIn('Summary and Signatures', html)
        self.assertIn('Total Students', html)
        self.assertIn('Pass Rate', html)

    def test_school_papers_print_the_school_phone_only(self):
        """A school result is the school's paper: the college has no part in it."""
        college_phone = settings.SCHOOL_INFO['college_phone']
        school_phone = settings.SCHOOL_INFO['school_phone']
        for name in ('result_sheet', 'published_results', 'exam_result_summary',
                     'top_10', 'exam_result_print_summary'):
            with self.subTest(page=name):
                paper = _paper(self.client.get(self.pages()[name]).content.decode())
                self.assertNotIn(college_phone, paper)
                self.assertNotIn('College:', paper)
                self.assertIn(school_phone, paper)

    def test_no_report_signs_as_a_principal(self):
        """A school is led by a Head Teacher; "Principal" has no place on a paper."""
        for name in ('result_sheet', 'published_results', 'top_10',
                     'exam_result_print_summary'):
            with self.subTest(page=name):
                paper = _paper(self.client.get(self.pages()[name]).content.decode())
                self.assertIn('Head Teacher', paper)
                # "Principal" survives only inside the institution's own name
                # ("Principal Kazi Faruky School"); it is never a signatory.
                for match in re.finditer('Principal', paper):
                    self.assertTrue(
                        paper.startswith('Principal Kazi Faruky', match.start()),
                        f'"Principal" used as a role on {name}',
                    )

    def test_signature_row_is_pinned_to_the_bottom_of_the_sheet(self):
        html = self.client.get(self.pages()['published_results']).content.decode()
        self.assertIn('.pr-sign-row {', html)
        self.assertRegex(html, r'\.pr-sign-row \{[^}]*margin-top: auto;')

    def test_published_sheet_footer_no_longer_carries_the_guide_line(self):
        html = self.client.get(self.pages()['published_results']).content.decode()
        footer = html.split('<footer class="pr-foot">', 1)[1].split('</footer>', 1)[0]
        self.assertNotIn('Guide Teacher', footer)
        self.assertIn('Page 1 of 1', footer)

    def test_base_print_masthead_has_the_logo_and_the_school_name(self):
        html = self.client.get(reverse('exam_list')).content.decode()
        masthead = html.split('<div class="print-header">', 1)[1].split('</div>\n    </div>', 1)[0]
        self.assertIn('school_logo.png', masthead)
        self.assertIn(settings.SCHOOL_INFO['school_name'], masthead)
        self.assertNotIn('School And College', masthead)


class CertificateAndCardChromeTests(TestCase):
    """The certificate, TC and ID card are school documents too."""

    @classmethod
    def setUpTestData(cls):
        cls.institution = Institution.objects.create(
            name='Principal Kazi Faruky School And College', classes='6',
        )
        cls.user = get_user_model().objects.create_superuser('doc-admin', 'd@example.com', 'password')
        cls.student = Student.objects.create(
            institution=cls.institution, student_id='DOC001', name='Doc Student',
            admission_class='6', section='A', roll_no=1, admission_year=2026,
        )
        cls.certificate = Certificate.objects.create(
            student=cls.student, certificate_type='TESTIMONIAL',
            certificate_number='CERT-1',
        )

    def setUp(self):
        self.client.force_login(self.user)

    def test_certificate_and_id_card_print_the_logo_only(self):
        pages = {
            'certificate': reverse('view_certificate', args=[self.certificate.pk]),
            'id_card': reverse('student_id_card', args=[self.student.pk]),
        }
        for name, url in pages.items():
            with self.subTest(page=name):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                html = response.content.decode()
                self.assertIn('school_logo.png', html)
                self.assertNotIn('School And College', html)
                self.assertIn('Principal Kazi Faruky School', html)

    def test_certificate_is_signed_by_the_head_teacher(self):
        """A school certificate is signed by the Head Teacher, not a Principal."""
        html = self.client.get(
            reverse('view_certificate', args=[self.certificate.pk])
        ).content.decode()
        self.assertIn("Head Teacher's Signature", html)
        self.assertNotIn("Principal's Signature", html)
