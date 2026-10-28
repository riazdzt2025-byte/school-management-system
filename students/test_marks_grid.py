"""Result Grid — the whole class on one sheet.

The grid is the paper register the office already keeps: every student down
the side, every subject (and every part of it) across the top, with the result
columns on the right. These tests pin down the two promises that make it safe
to hand to a teacher:

1. **The students are the exam's own cohort.** Nothing is typed in or imported
   here — the page opens already filled from the class/section/group register
   the marks pages and the result sheet use (``get_exam_students``).
2. **The grid is not a second result engine.** It writes ``ExamMark`` rows
   through the same part rules Enter Marks enforces, and the Total / GPA /
   Grade / Position it shows come from ``build_exam_results``.
"""
import json
import re
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import (
    Exam, ExamMark, Institution, Student, StudentSubjectChoice, Subject,
    SubjectMarkSetting, SubjectRequirement,
)
from .permissions import ensure_default_groups, sync_user_department_permissions
from .models import InstitutionAccess


def assign(institution, subject, admission_class='9', group='',
           requirement_type='MANDATORY'):
    return SubjectRequirement.objects.create(
        institution=institution,
        admission_class=admission_class,
        group=group,
        subject=subject,
        requirement_type=requirement_type,
    )


class ResultGridTests(TestCase):
    def setUp(self):
        self.institution = Institution.objects.create(name='Grid School', classes='9')
        self.user = get_user_model().objects.create_superuser(
            'gridadmin', 'grid@example.com', 'password',
        )
        self.client.force_login(self.user)

        # Bangla has no split (one total box); Physics splits into CQ + Weekly
        # Test, exactly the Mid Term shape the paper register uses.
        self.bangla = Subject.objects.create(code='101', name='Bangla', full_marks=100)
        self.physics = Subject.objects.create(
            code='136', name='Physics', full_marks=60, cq_marks=45,
        )
        self.chemistry = Subject.objects.create(code='137', name='Chemistry', full_marks=100)
        assign(self.institution, self.bangla)
        assign(self.institution, self.physics)
        self.chemistry_requirement = assign(
            self.institution, self.chemistry, requirement_type='OPTIONAL',
        )
        SubjectMarkSetting.objects.create(
            institution=self.institution, admission_class='9', subject=self.physics,
            exam_type='MID_TERM_1', group='', full_marks=60, cq_marks=45,
            weekly_test_marks=15,
        )
        SubjectMarkSetting.objects.create(
            institution=self.institution, admission_class='9', subject=self.bangla,
            exam_type='MID_TERM_1', group='', full_marks=100,
        )

        self.exam = Exam.objects.create(
            name='Mid Term 2026', exam_type='MID_TERM_1', institution=self.institution,
            admission_class='9', section='', session='2026',
        )
        self.alice = Student.objects.create(
            institution=self.institution, student_id='G001', name='Alice Akter',
            admission_class='9', section='A', roll_no=1, admission_year=2026,
            guardian_contact_no='01812345678',
        )
        self.bob = Student.objects.create(
            institution=self.institution, student_id='G002', name='Bob Hossain',
            admission_class='9', section='A', roll_no=2, admission_year=2026,
            guardian_contact_no='01812345679',
        )
        # Only Alice takes the optional Chemistry paper; Bob does not.
        StudentSubjectChoice.objects.create(
            student=self.alice, requirement=self.chemistry_requirement,
        )
        self.grid_url = reverse('marks_grid', args=[self.exam.pk])
        self.save_url = reverse('marks_grid_save', args=[self.exam.pk])

    # ---------- the previous method: students come from the exam ----------

    def test_grid_lists_the_exam_cohort_without_any_manual_entry(self):
        response = self.client.get(self.grid_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Alice Akter')
        self.assertContains(response, 'Bob Hossain')
        self.assertContains(response, 'id="marks-grid-table"')
        # The page has no student-entry control of its own: the register (the
        # exam's cohort) is the only source of rows.
        self.assertNotContains(response, 'id="add-student"')

    def test_grid_shows_one_box_per_configured_part(self):
        response = self.client.get(self.grid_url)
        content = response.content.decode()

        def collects(subject, part):
            return re.search(
                r'data-subject="%d"\s+data-part="%s"' % (subject, part), content,
            ) is not None

        # Physics: CQ 45 + Weekly Test 15, plus the derived "প্রাপ্ত" column.
        self.assertTrue(collects(self.physics.pk, 'cq'))
        self.assertTrue(collects(self.physics.pk, 'weekly_test'))
        # Bangla has no split, so it is a single whole-total box.
        self.assertTrue(collects(self.bangla.pk, 'total'))
        self.assertFalse(collects(self.bangla.pk, 'cq'))

    def test_subject_a_student_did_not_choose_has_no_input_for_them(self):
        html = self.client.get(self.grid_url).content.decode()
        # Alice sits Chemistry (she chose it), Bob does not: exactly one input
        # carries that subject, and Bob's own cell is the inert dash.
        self.assertEqual(
            html.count('data-subject="%d"' % self.chemistry.pk), 1,
            'Bob should not get a Chemistry input',
        )
        self.assertIn('data-grid-cell="%d-%d"' % (self.bob.pk, self.chemistry.pk), html)

    def test_subject_nobody_has_marked_yet_is_a_dash_not_a_fail(self):
        # A subject assigned to the class but not yet marked is not a result
        # column, so the grid must not paint every student red for it.
        extra = Subject.objects.create(code='140', name='ICT', full_marks=100)
        assign(self.institution, extra)
        SubjectMarkSetting.objects.create(
            institution=self.institution, admission_class='9', subject=extra,
            exam_type='MID_TERM_1', group='', full_marks=100,
        )

        def cell_of(response, student, subject):
            row = next(
                item for item in response.context['rows']
                if item['student_pk'] == student.pk
            )
            item = next(
                entry for entry in row['cells']
                if entry['column']['subject'].pk == subject.pk
            )
            return item['cell']

        before = cell_of(self.client.get(self.grid_url), self.bob, extra)
        self.assertTrue(before['absent'])
        self.assertFalse(before['failed'])
        self.assertEqual(before['grade'], '')

        # Once one student has a mark, the subject is a real column and an
        # unmarked student grades F, exactly like the result sheet.
        self._post_changes([
            {'student': self.alice.pk, 'subject': extra.pk, 'part': 'total', 'value': '80'},
        ])
        after = cell_of(self.client.get(self.grid_url), self.bob, extra)
        self.assertTrue(after['absent'])
        self.assertTrue(after['failed'])

    # ---------- saving one cell at a time ----------

    def _post_changes(self, changes):
        return self.client.post(
            self.save_url,
            data=json.dumps({'changes': changes}),
            content_type='application/json',
        )

    def test_saving_a_part_stores_every_part_and_the_sum(self):
        response = self._post_changes([
            {'student': self.alice.pk, 'subject': self.physics.pk, 'part': 'cq', 'value': '40'},
            {'student': self.alice.pk, 'subject': self.physics.pk, 'part': 'weekly_test', 'value': '12'},
        ])
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['ok'])
        mark = ExamMark.objects.get(exam=self.exam, student=self.alice, subject=self.physics)
        self.assertEqual(mark.cq_obtained, Decimal('40'))
        self.assertEqual(mark.weekly_test_obtained, Decimal('12'))
        self.assertEqual(mark.marks_obtained, Decimal('52'))

    def test_saving_one_part_keeps_the_other_part(self):
        ExamMark.objects.create(
            exam=self.exam, student=self.alice, subject=self.physics,
            marks_obtained=Decimal('50'), cq_obtained=Decimal('38'),
            weekly_test_obtained=Decimal('12'),
        )
        response = self._post_changes([
            {'student': self.alice.pk, 'subject': self.physics.pk, 'part': 'cq', 'value': '42'},
        ])
        self.assertEqual(response.status_code, 200)
        mark = ExamMark.objects.get(exam=self.exam, student=self.alice, subject=self.physics)
        self.assertEqual(mark.cq_obtained, Decimal('42'))
        self.assertEqual(mark.weekly_test_obtained, Decimal('12'))
        self.assertEqual(mark.marks_obtained, Decimal('54'))

    def test_response_carries_the_recalculated_result_of_the_row(self):
        response = self._post_changes([
            {'student': self.alice.pk, 'subject': self.physics.pk, 'part': 'cq', 'value': '42'},
            {'student': self.alice.pk, 'subject': self.physics.pk, 'part': 'weekly_test', 'value': '13'},
            {'student': self.alice.pk, 'subject': self.bangla.pk, 'part': 'total', 'value': '76'},
        ])
        row = next(
            item for item in response.json()['rows'] if item['student'] == self.alice.pk
        )
        self.assertEqual(row['total'], 131)
        self.assertNotEqual(row['grade'], '')
        obtained = {cell['subject']: cell['obtained'] for cell in row['cells']}
        self.assertEqual(obtained[self.bangla.pk], 76)
        self.assertEqual(obtained[self.physics.pk], 55)

    def test_bangla_digits_are_accepted(self):
        response = self._post_changes([
            {'student': self.bob.pk, 'subject': self.bangla.pk, 'part': 'total', 'value': '৭৬'},
        ])
        self.assertTrue(response.json()['ok'])
        mark = ExamMark.objects.get(exam=self.exam, student=self.bob, subject=self.bangla)
        self.assertEqual(mark.marks_obtained, Decimal('76'))

    def test_mark_above_the_part_maximum_is_refused(self):
        response = self._post_changes([
            {'student': self.alice.pk, 'subject': self.physics.pk, 'part': 'cq', 'value': '46'},
        ])
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload['ok'])
        self.assertIn('must be between 0 and 45', payload['errors'][0])
        self.assertFalse(
            ExamMark.objects.filter(exam=self.exam, student=self.alice, subject=self.physics).exists()
        )

    def test_mark_for_a_subject_the_student_does_not_sit_is_refused(self):
        response = self._post_changes([
            {'student': self.bob.pk, 'subject': self.chemistry.pk, 'part': 'total', 'value': '70'},
        ])
        payload = response.json()
        self.assertFalse(payload['ok'])
        self.assertIn('is not one of this student', payload['errors'][0])
        self.assertFalse(
            ExamMark.objects.filter(exam=self.exam, student=self.bob, subject=self.chemistry).exists()
        )

    def test_a_different_institution_student_is_refused(self):
        other = Institution.objects.create(name='Other Grid School', classes='9')
        outsider = Student.objects.create(
            institution=other, student_id='O001', name='Outsider',
            admission_class='9', section='A', roll_no=1, admission_year=2026,
            guardian_contact_no='01812345670',
        )
        response = self._post_changes([
            {'student': outsider.pk, 'subject': self.bangla.pk, 'part': 'total', 'value': '70'},
        ])
        self.assertFalse(response.json()['ok'])
        self.assertFalse(ExamMark.objects.filter(student=outsider).exists())

    def test_clearing_every_box_drops_the_mark_row(self):
        ExamMark.objects.create(
            exam=self.exam, student=self.alice, subject=self.physics,
            marks_obtained=Decimal('50'), cq_obtained=Decimal('38'),
            weekly_test_obtained=Decimal('12'),
        )
        self._post_changes([
            {'student': self.alice.pk, 'subject': self.physics.pk, 'part': 'cq', 'value': ''},
            {'student': self.alice.pk, 'subject': self.physics.pk, 'part': 'weekly_test', 'value': ''},
        ])
        self.assertFalse(
            ExamMark.objects.filter(exam=self.exam, student=self.alice, subject=self.physics).exists()
        )

    def test_clearing_a_whole_total_box_drops_the_mark_row(self):
        ExamMark.objects.create(
            exam=self.exam, student=self.alice, subject=self.bangla,
            marks_obtained=Decimal('70'),
        )
        self._post_changes([
            {'student': self.alice.pk, 'subject': self.bangla.pk, 'part': 'total', 'value': ''},
        ])
        self.assertFalse(
            ExamMark.objects.filter(exam=self.exam, student=self.alice, subject=self.bangla).exists()
        )

    def test_golden_a_plus_and_the_live_summary(self):
        response = self._post_changes([
            {'student': self.alice.pk, 'subject': self.bangla.pk, 'part': 'total', 'value': '85'},
            {'student': self.alice.pk, 'subject': self.physics.pk, 'part': 'cq', 'value': '42'},
            {'student': self.alice.pk, 'subject': self.physics.pk, 'part': 'weekly_test', 'value': '13'},
            {'student': self.alice.pk, 'subject': self.chemistry.pk, 'part': 'total', 'value': '82'},
        ])
        payload = response.json()
        alice = next(row for row in payload['rows'] if row['student'] == self.alice.pk)
        self.assertEqual(alice['grade'], 'A+')
        self.assertTrue(alice['golden'])
        # The chips above the sheet move with the save, not only on reload.
        self.assertEqual(payload['summary']['passed'], 1)
        self.assertEqual(payload['summary']['no_marks'], 1)
        self.assertEqual(payload['summary']['golden'], 1)

    # ---------- published lock ----------

    def test_published_exam_marks_are_locked_and_an_attempt_is_flagged(self):
        self.exam.is_published = True
        self.exam.save(update_fields=['is_published'])
        response = self._post_changes([
            {'student': self.alice.pk, 'subject': self.bangla.pk, 'part': 'total', 'value': '70'},
        ])
        self.assertEqual(response.status_code, 403)
        self.assertTrue(response.json()['locked'])
        self.assertFalse(ExamMark.objects.exists())

    # ---------- access ----------

    def test_login_is_required(self):
        self.client.logout()
        response = self.client.get(self.grid_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response['Location'])

    def test_viewer_without_the_add_permission_sees_a_read_only_sheet(self):
        ensure_default_groups()
        viewer = get_user_model().objects.create_user('grid-viewer', password='pw')
        InstitutionAccess.objects.create(
            user=viewer, institution=self.institution, department='Office',
        )
        sync_user_department_permissions(viewer)
        # A department clerk may view, but only mark-writing permission edits.
        viewer.user_permissions.clear()
        self.client.force_login(viewer)
        response = self.client.get(self.grid_url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'class="mg-input"')
        self.assertFalse(response.context['can_edit_marks'])
