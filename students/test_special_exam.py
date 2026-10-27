"""Special exam (বৃত্তি পরীক্ষা) — candidates and papers picked by hand.

An ordinary exam is a register: its cohort is *class + section + group* and
its papers are the ones assigned to that class. A special exam is the
opposite — the office ticks the candidates (from any class) and the papers
when the exam is created, so any student can sit it.

Everything downstream (marks entry, Excel import, result sheet, merit list,
top 10, seat plan) reads the cohort and the papers through
``get_exam_students`` / ``get_exam_subjects``, so hooking the hand-picked
lists in there is what makes the whole flow work.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import (
    Exam, ExamMark, Institution, Student, Subject, SubjectMarkSetting, SubjectRequirement,
)
from .result_utils import (
    build_exam_results, get_exam_students, get_exam_subjects, get_student_subject_ids,
)


class SpecialExamFixtureMixin:
    def build_fixture(self):
        self.institution = Institution.objects.create(
            name='Special Exam School', classes='8,9,10',
        )
        self.other_institution = Institution.objects.create(name='Other School', classes='8')
        self.user = get_user_model().objects.create_superuser(
            'specialexam', 'se@example.com', 'password',
        )

        self.bangla = Subject.objects.create(code='BANS', name='Bangla', full_marks=100)
        self.english = Subject.objects.create(code='ENGS', name='English', full_marks=100)
        self.math = Subject.objects.create(code='MATHS', name='Mathematics', full_marks=100)
        self.physics = Subject.objects.create(code='PHYS', name='Physics', full_marks=100)

        # Class 8 has the usual register; class 9 has Physics for Science only.
        SubjectRequirement.objects.create(institution=self.institution, admission_class='8', group='', subject=self.bangla)
        SubjectRequirement.objects.create(institution=self.institution, admission_class='8', group='', subject=self.english)
        SubjectRequirement.objects.create(institution=self.institution, admission_class='9', group='SCI', subject=self.physics)

        self.class8_a = self._student('S8001', 'Ayesha', '8')
        self.class8_b = self._student('S8002', 'Rakib', '8')
        self.class9_sci = self._student('S9001', 'Tania', '9', group='SCI')
        self.outsider = self._student('S9002', 'Nadim', '9', institution=self.other_institution)
        self.left_school = self._student('S8003', 'Old Student', '8', status='DISCONTINUED')

    def _student(self, student_id, name, admission_class, group='', status='ACTIVE', institution=None):
        return Student.objects.create(
            institution=institution or self.institution,
            student_id=student_id, name=name, admission_class=admission_class,
            section='A', group=group, status=status,
            guardian_contact_no='01810000000',
        )

    def build_special_exam(self, students, subjects):
        exam = Exam.objects.create(
            name='Scholarship Test-2026', exam_type='SECOND_TERM',
            institution=self.institution, admission_class='8', session='2026',
            is_special=True,
        )
        exam.special_students.set(students)
        exam.special_subjects.set(subjects)
        return exam


class SpecialExamCohortTests(SpecialExamFixtureMixin, TestCase):
    def setUp(self):
        self.build_fixture()

    def test_cohort_is_the_hand_picked_list(self):
        exam = self.build_special_exam(
            [self.class8_a, self.class9_sci], [self.bangla, self.math],
        )
        self.assertEqual(
            list(get_exam_students(exam)), [self.class8_a, self.class9_sci],
        )

    def test_cohort_ignores_class_section_and_group(self):
        """A class-9 Science student sits a class-8 exam because they were ticked."""
        exam = self.build_special_exam([self.class9_sci], [self.bangla])
        exam.section = 'A'
        exam.group = 'SCI'
        exam.save()
        self.assertEqual(list(get_exam_students(exam)), [self.class9_sci])

    def test_archived_and_inactive_candidates_are_dropped(self):
        exam = self.build_special_exam(
            [self.class8_a, self.left_school], [self.bangla],
        )
        self.assertEqual(list(get_exam_students(exam)), [self.class8_a])

    def test_papers_are_the_picked_ones(self):
        exam = self.build_special_exam(
            [self.class8_a], [self.bangla, self.math],
        )
        subjects, is_filtered = get_exam_subjects(exam)
        self.assertEqual(subjects, [self.bangla, self.math])
        self.assertTrue(is_filtered)

    def test_paper_switched_off_in_mark_evaluation_stays_off(self):
        """"Reuse Mark Evaluation" includes its Count tick."""
        SubjectMarkSetting.objects.create(
            institution=self.institution, admission_class='8', subject=self.math,
            exam_type='SECOND_TERM', group='', full_marks=100, is_active=False,
        )
        exam = self.build_special_exam([self.class8_a], [self.bangla, self.math])
        subjects, _is_filtered = get_exam_subjects(exam)
        self.assertEqual(subjects, [self.bangla])

    def test_every_candidate_sits_every_picked_paper(self):
        exam = self.build_special_exam(
            [self.class8_a, self.class9_sci], [self.bangla, self.physics],
        )
        students = list(get_exam_students(exam))
        subjects, _ = get_exam_subjects(exam)
        per_student = get_student_subject_ids(exam, students, subjects=subjects)
        wanted = {self.bangla.pk, self.physics.pk}
        self.assertEqual(
            {student.pk: set(per_student[student.pk]) for student in students},
            {self.class8_a.pk: wanted, self.class9_sci.pk: wanted},
        )

    def test_ordinary_exam_still_follows_the_register(self):
        exam = Exam.objects.create(
            name='Second Term Examination-2026', exam_type='SECOND_TERM',
            institution=self.institution, admission_class='8', session='2026',
        )
        self.assertEqual(
            sorted(s.pk for s in get_exam_students(exam)),
            sorted([self.class8_a.pk, self.class8_b.pk]),
        )
        subjects, _ = get_exam_subjects(exam)
        self.assertEqual(subjects, [self.bangla, self.english])


class SpecialExamMarksTests(SpecialExamFixtureMixin, TestCase):
    def setUp(self):
        self.build_fixture()
        self.exam = self.build_special_exam(
            [self.class8_a, self.class9_sci], [self.bangla, self.math],
        )
        self.client.force_login(self.user)

    def test_subject_picker_offers_the_picked_papers(self):
        response = self.client.get(reverse('select_marks_subject', args=[self.exam.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            {subject.pk for subject in response.context['subjects']},
            {self.bangla.pk, self.math.pk},
        )
        self.assertEqual(len(response.context['students']), 2)

    def test_marks_entry_lists_only_the_candidates(self):
        response = self.client.get(
            reverse('enter_marks', args=[self.exam.pk, self.bangla.pk]),
        )
        self.assertEqual(response.status_code, 200)
        rows = response.context['students_with_marks']
        self.assertEqual([row['student'].pk for row in rows],
                         [self.class8_a.pk, self.class9_sci.pk])
        self.assertContains(response, 'Special exam')

    def test_saving_marks_reaches_the_candidates(self):
        response = self.client.post(
            reverse('enter_marks', args=[self.exam.pk, self.bangla.pk]),
            {
                f'marks_{self.class8_a.pk}': '80',
                f'marks_{self.class9_sci.pk}': '91',
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ExamMark.objects.filter(exam=self.exam).count(), 2)
        self.assertEqual(
            ExamMark.objects.get(exam=self.exam, student=self.class9_sci).marks_obtained,
            Decimal('91'),
        )


class SpecialExamResultTests(SpecialExamFixtureMixin, TestCase):
    def setUp(self):
        self.build_fixture()
        self.exam = self.build_special_exam(
            [self.class8_a, self.class9_sci], [self.bangla, self.math],
        )
        ExamMark.objects.create(exam=self.exam, student=self.class8_a, subject=self.bangla, marks_obtained=Decimal('70'))
        ExamMark.objects.create(exam=self.exam, student=self.class8_a, subject=self.math, marks_obtained=Decimal('80'))
        ExamMark.objects.create(exam=self.exam, student=self.class9_sci, subject=self.bangla, marks_obtained=Decimal('90'))
        ExamMark.objects.create(exam=self.exam, student=self.class9_sci, subject=self.math, marks_obtained=Decimal('85'))

    def test_result_covers_only_the_candidates(self):
        _columns, results = build_exam_results(self.exam)
        self.assertEqual(
            {result['student'].pk for result in results},
            {self.class8_a.pk, self.class9_sci.pk},
        )
        positions = {result['student'].pk: result['position'] for result in results}
        # Merit order over the hand-picked cohort: 175 before 150.
        self.assertEqual(positions[self.class9_sci.pk], 1)
        self.assertEqual(positions[self.class8_a.pk], 2)

    def test_result_sheet_renders(self):
        self.exam.is_published = True
        self.exam.save()
        user = get_user_model().objects.create_superuser('seviewer', 'v@example.com', 'password')
        self.client.force_login(user)
        response = self.client.get(reverse('result_sheet', args=[self.exam.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Ayesha')
        self.assertContains(response, 'Tania')


class SpecialExamFormTests(SpecialExamFixtureMixin, TestCase):
    def setUp(self):
        self.build_fixture()
        self.client.force_login(self.user)

    def _post(self, **overrides):
        data = {
            'institution': self.institution.pk,
            'admission_class': '8',
            'section': 'A',
            'group': '',
            'exam_type': 'SECOND_TERM',
            'session': '2026',
            'is_special': 'on',
            'special_students': [self.class8_a.pk, self.class9_sci.pk],
            'special_subjects': [self.bangla.pk, self.math.pk],
        }
        data.update(overrides)
        return self.client.post(reverse('add_exam'), data)

    def test_special_exam_saves_the_picks(self):
        response = self._post()
        self.assertEqual(response.status_code, 302)
        exam = Exam.objects.get(institution=self.institution, is_special=True)
        self.assertEqual(
            set(exam.special_students.values_list('pk', flat=True)),
            {self.class8_a.pk, self.class9_sci.pk},
        )
        self.assertEqual(
            set(exam.special_subjects.values_list('pk', flat=True)),
            {self.bangla.pk, self.math.pk},
        )

    def test_special_exam_ignores_section_and_group(self):
        self._post(section='A', group='SCI')
        exam = Exam.objects.get(institution=self.institution, is_special=True)
        self.assertEqual(exam.section, '')
        self.assertEqual(exam.group, '')

    def test_candidates_are_required(self):
        response = self._post(special_students=[])
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Exam.objects.filter(is_special=True).exists())
        self.assertContains(response, 'Tick at least one candidate')

    def test_papers_are_required(self):
        response = self._post(special_subjects=[])
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Exam.objects.filter(is_special=True).exists())
        self.assertContains(response, 'Tick at least one paper')

    def test_candidate_from_another_institution_is_rejected(self):
        response = self._post(special_students=[self.class8_a.pk, self.outsider.pk])
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Exam.objects.filter(is_special=True).exists())
        self.assertContains(response, 'do not belong to')

    def test_ordinary_exam_drops_the_pickers(self):
        response = self._post(
            is_special='',
            special_students=[self.class8_a.pk],
            special_subjects=[self.bangla.pk],
        )
        self.assertEqual(response.status_code, 302)
        exam = Exam.objects.get(institution=self.institution, is_special=False)
        self.assertEqual(exam.special_students.count(), 0)
        self.assertEqual(exam.special_subjects.count(), 0)

    def test_unticking_special_clears_a_saved_list(self):
        exam = self.build_special_exam([self.class8_a], [self.bangla])
        response = self.client.post(reverse('edit_exam', args=[exam.pk]), {
            'institution': self.institution.pk,
            'admission_class': '8',
            'section': '',
            'group': '',
            'exam_type': 'SECOND_TERM',
            'session': '2026',
        })
        self.assertEqual(response.status_code, 302)
        exam.refresh_from_db()
        self.assertFalse(exam.is_special)
        self.assertEqual(exam.special_students.count(), 0)
        self.assertEqual(exam.special_subjects.count(), 0)

    def test_candidate_rows_carry_class_and_institution(self):
        """The browser picker narrows the list by the exam's class/institution."""
        response = self.client.get(reverse('add_exam'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'data-institution="{self.institution.pk}"')
        self.assertContains(response, 'data-class="8"')
        self.assertContains(response, 'data-class="9"')

    def test_edit_form_preselects_the_saved_candidates(self):
        exam = self.build_special_exam([self.class9_sci], [self.math])
        response = self.client.get(reverse('edit_exam', args=[exam.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['selected_special_student_ids'], [self.class9_sci.pk])
        self.assertEqual(response.context['selected_special_subject_ids'], [self.math.pk])
