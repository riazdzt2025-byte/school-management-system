"""A4 report cards — one printed page per student, from the same results.

The card is the sheet a guardian carries home, so the tests pin down what must
never drift:

1. **The numbers are the result sheet's numbers** — every total, grade, GPA and
   position on a card comes from ``build_exam_results``.
2. **One page per student**, in register (roll) order, with the merged Religion
   column printed as the paper that student actually sits.
3. **The layout is A4 portrait** and prints black on white; the whole class can
   be printed at once, or a single student reprinted with ``?student=<pk>``.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import (
    Exam, ExamMark, Institution, InstitutionAccess, Student, Subject,
    SubjectMarkSetting, SubjectRequirement,
)
from .permissions import ensure_default_groups, sync_user_department_permissions
from .result_utils import build_exam_results


def assign(institution, subject, admission_class='9', group='', requirement_type='MANDATORY'):
    return SubjectRequirement.objects.create(
        institution=institution, admission_class=admission_class, group=group,
        subject=subject, requirement_type=requirement_type,
    )


class ReportCardTests(TestCase):
    def setUp(self):
        self.institution = Institution.objects.create(name='Card School', classes='9')
        self.user = get_user_model().objects.create_superuser(
            'cardadmin', 'card@example.com', 'password',
        )
        self.client.force_login(self.user)

        self.bangla = Subject.objects.create(code='101', name='Bangla', full_marks=100)
        self.physics = Subject.objects.create(
            code='136', name='Physics', full_marks=60, cq_marks=45,
        )
        assign(self.institution, self.bangla)
        assign(self.institution, self.physics)
        SubjectMarkSetting.objects.create(
            institution=self.institution, admission_class='9', subject=self.bangla,
            exam_type='MID_TERM_1', group='', full_marks=100,
        )
        SubjectMarkSetting.objects.create(
            institution=self.institution, admission_class='9', subject=self.physics,
            exam_type='MID_TERM_1', group='', full_marks=60, cq_marks=45,
            weekly_test_marks=15,
        )
        self.exam = Exam.objects.create(
            name='Mid Term 2026', exam_type='MID_TERM_1', institution=self.institution,
            admission_class='9', session='2026',
        )
        self.alice = Student.objects.create(
            institution=self.institution, student_id='C001', name='Alice Akter',
            admission_class='9', section='A', roll_no=1, admission_year=2026,
            guardian_contact_no='01812345678',
        )
        self.bob = Student.objects.create(
            institution=self.institution, student_id='C002', name='Bob Hossain',
            admission_class='9', section='A', roll_no=2, admission_year=2026,
            guardian_contact_no='01812345679',
        )
        ExamMark.objects.create(
            exam=self.exam, student=self.alice, subject=self.bangla,
            marks_obtained=Decimal('86'),
        )
        ExamMark.objects.create(
            exam=self.exam, student=self.alice, subject=self.physics,
            marks_obtained=Decimal('52'), cq_obtained=Decimal('40'),
            weekly_test_obtained=Decimal('12'),
        )
        ExamMark.objects.create(
            exam=self.exam, student=self.bob, subject=self.bangla,
            marks_obtained=Decimal('45'),
        )
        ExamMark.objects.create(
            exam=self.exam, student=self.bob, subject=self.physics,
            marks_obtained=Decimal('30'), cq_obtained=Decimal('22'),
            weekly_test_obtained=Decimal('8'),
        )
        self.url = reverse('exam_report_cards', args=[self.exam.pk])

    def _cards(self, response):
        return response.context['cards']

    # ---------- one page per student, in register order ----------

    def test_one_card_per_student_in_roll_order(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        cards = self._cards(response)
        self.assertEqual(
            [card['student'].pk for card in cards], [self.alice.pk, self.bob.pk],
        )
        self.assertEqual(response.content.decode().count('<section class="rc-sheet">'), 2)

    def test_a_single_student_can_be_reprinted(self):
        response = self.client.get(self.url, {'student': self.bob.pk})
        cards = self._cards(response)
        self.assertEqual([card['student'].pk for card in cards], [self.bob.pk])
        # One printed sheet only. Alice still appears in the on-screen picker
        # (that is the selector listing the class), never as a card.
        html = response.content.decode()
        sheets = html.split('<section class="rc-sheet">')[1:]
        self.assertEqual(len(sheets), 1)
        self.assertIn('Bob Hossain', sheets[0])
        self.assertNotIn('Alice Akter', sheets[0])

    # ---------- the numbers are the result sheet's numbers ----------

    def test_card_numbers_match_build_exam_results(self):
        _columns, results = build_exam_results(self.exam)
        by_student = {result['student'].pk: result for result in results}
        cards = {card['student'].pk: card for card in self._cards(self.client.get(self.url))}

        for pk, result in by_student.items():
            card = cards[pk]
            self.assertEqual(card['gpa'], f"{Decimal(result['gpa']):.2f}")
            self.assertEqual(card['grade'], result['grade'])
            self.assertEqual(card['status'], result['status'])
            self.assertEqual(card['position'], result['position'])
            self.assertEqual(card['total'], int(result['total_obtained']))

    def test_part_marks_are_printed_for_each_subject(self):
        response = self.client.get(self.url, {'student': self.alice.pk})
        card = self._cards(response)[0]
        physics = next(row for row in card['rows'] if row['name'] == 'Physics')
        values = {cell['label']: cell['value'] for cell in physics['cells']}
        self.assertEqual(values['CQ'], 40)
        self.assertEqual(values['Weekly Test'], 12)
        self.assertEqual(physics['obtained'], 52)
        # Bangla has no split: its single total is the whole mark.
        bangla = next(row for row in card['rows'] if row['name'] == 'Bangla')
        self.assertEqual(bangla['obtained'], 86)

    def test_grade_scale_and_comment_are_printed(self):
        html = self.client.get(self.url, {'student': self.alice.pk}).content.decode()
        for label in ['80% +', '70–79%', '33–39%', '0–32%']:
            self.assertIn(label, html)
        card = self._cards(self.client.get(self.url, {'student': self.alice.pk}))[0]
        self.assertEqual(card['comment'], 'Excellent Result')

    def test_failed_subject_lowers_the_result_not_the_card(self):
        # Bob's Physics is 30/60 = 50%, which passes; drop it below 40% and the
        # whole result must read Fail with GPA 0.00 on his card.
        ExamMark.objects.filter(
            exam=self.exam, student=self.bob, subject=self.physics,
        ).update(marks_obtained=Decimal('20'), cq_obtained=Decimal('15'),
                 weekly_test_obtained=Decimal('5'))
        card = self._cards(self.client.get(self.url, {'student': self.bob.pk}))[0]
        self.assertEqual(card['status'], 'Fail')
        self.assertEqual(card['gpa'], '0.00')
        self.assertEqual(card['grade'], 'F')
        self.assertIsNone(card['position'])
        self.assertEqual(card['fails'], 1)
        self.assertEqual(card['comment'], 'Badly Fail')

    def test_a_student_with_no_marks_prints_an_empty_card_not_a_fail(self):
        carol = Student.objects.create(
            institution=self.institution, student_id='C003', name='Carol Noor',
            admission_class='9', section='A', roll_no=3, admission_year=2026,
            guardian_contact_no='01812345670',
        )
        card = self._cards(self.client.get(self.url, {'student': carol.pk}))[0]
        self.assertFalse(card['has_marks'])
        self.assertIsNone(card['total'])
        self.assertEqual(card['status'], 'No Marks')

    def test_mixed_parts_and_the_merged_religion_column(self):
        # Physics splits CQ + Weekly, Bangla has one total box, and the two
        # religion papers print as ONE column carrying the student's own paper.
        islam = Subject.objects.create(
            code='150', name='Islam & Moral Education', full_marks=50, category='RELIGION',
        )
        Hindu = Subject.objects.create(
            code='151', name='Hindu Religion & Moral Education', full_marks=50,
            category='RELIGION',
        )
        SubjectRequirement.objects.create(
            institution=self.institution, admission_class='9', group='',
            subject=islam, requirement_type='CONDITIONAL',
            condition_religion='Islam',
        )
        SubjectRequirement.objects.create(
            institution=self.institution, admission_class='9', group='',
            subject=Hindu, requirement_type='CONDITIONAL',
            condition_religion='Hindu',
        )
        self.alice.religion = 'Islam'
        self.alice.save(update_fields=['religion'])
        self.bob.religion = 'Hindu'
        self.bob.save(update_fields=['religion'])
        ExamMark.objects.create(
            exam=self.exam, student=self.alice, subject=islam, marks_obtained=Decimal('44'),
        )
        ExamMark.objects.create(
            exam=self.exam, student=self.bob, subject=Hindu, marks_obtained=Decimal('38'),
        )

        response = self.client.get(self.url)
        cards = {card['student'].pk: card for card in self._cards(response)}
        # Exactly one religion row per card, carrying that student's own paper
        # (the two papers are merged into one column, never printed twice).
        html = response.content.decode()
        self.assertEqual(html.count('Islam &amp; Moral Education'), 1)
        self.assertEqual(html.count('Hindu Religion &amp; Moral Education'), 1)

        alice_religion = [
            row for row in cards[self.alice.pk]['rows']
            if row['name'] == 'Islam & Moral Education'
        ]
        bob_religion = [
            row for row in cards[self.bob.pk]['rows']
            if row['name'] == 'Hindu Religion & Moral Education'
        ]
        self.assertEqual(len(alice_religion), 1)
        self.assertEqual(len(bob_religion), 1)
        self.assertEqual(alice_religion[0]['obtained'], 44)
        self.assertEqual(bob_religion[0]['obtained'], 38)

        # A subject with a different split still prints the columns the class
        # shares, with a dash in the box it does not have.
        labels = response.context['part_columns']
        self.assertEqual(
            [part['label'] for part in labels], ['CQ', 'Weekly Test'],
        )

    # ---------- the paper itself ----------

    def test_page_is_a4_portrait(self):
        html = self.client.get(self.url).content.decode()
        self.assertIn('size: A4 portrait', html)

    def test_unpublished_exam_is_printed_as_a_draft(self):
        html = self.client.get(self.url).content.decode()
        self.assertIn('DRAFT', html)
        self.exam.is_published = True
        self.exam.save(update_fields=['is_published'])
        html = self.client.get(self.url).content.decode()
        self.assertNotIn('DRAFT', html)

    def test_login_is_required(self):
        self.client.logout()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response['Location'])

    def test_another_institutions_exam_is_not_reachable(self):
        other = Institution.objects.create(name='Other Card School', classes='9')
        outsider = get_user_model().objects.create_user('card-outsider', password='pw')
        ensure_default_groups()
        InstitutionAccess.objects.create(
            user=outsider, institution=other, department='Exam',
        )
        sync_user_department_permissions(outsider)
        self.client.force_login(outsider)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 404)

    def test_school_letterhead_comes_from_school_info(self):
        response = self.client.get(self.url)
        self.assertContains(response, response.context['SCHOOL_INFO']['name'])
