from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import reverse

from .forms import ExamForm
from .models import (
    Exam, ExamMark, Institution, InstitutionAccess, SpecialExamRankOrder, Student, Subject,
    SubjectRequirement,
)


class SpecialExamResultTests(TestCase):
    def setUp(self):
        self.institution = Institution.objects.create(
            name='Special Result School', classes='6,7',
        )
        self.subject = Subject.objects.create(
            code='ENG', name='English', full_marks=100,
        )
        SubjectRequirement.objects.create(
            institution=self.institution, admission_class='6',
            subject=self.subject, requirement_type='MANDATORY',
        )
        self.exam = Exam.objects.create(
            name='Special Exam Examination-2026',
            exam_type='SPECIAL_EXAM',
            institution=self.institution,
            admission_class='6',
            session='2026',
            is_published=True,
            special_result_enabled=True,
        )
        self.roll_three = Student.objects.create(
            institution=self.institution, student_id='SP003',
            name='Candidate Three', admission_class='6', roll_no=3,
        )
        self.roll_one = Student.objects.create(
            institution=self.institution, student_id='SP001',
            name='Candidate One', admission_class='6', roll_no=1,
        )
        self.roll_two = Student.objects.create(
            institution=self.institution, student_id='SP002',
            name='Candidate Two', admission_class='6', roll_no=2,
        )
        for student, marks in (
            (self.roll_three, 80), (self.roll_one, 80), (self.roll_two, 70),
        ):
            ExamMark.objects.create(
                exam=self.exam, student=student, subject=self.subject,
                marks_obtained=marks,
            )
        self.user = get_user_model().objects.create_user(
            username='special-exam-editor', password='pw',
        )
        permission = Permission.objects.get(
            content_type=ContentType.objects.get_for_model(Exam),
            codename='change_exam',
        )
        self.user.user_permissions.add(permission)
        self.client.force_login(self.user)

    def _report(self):
        return self.client.get(
            reverse('special_exam_result_list'),
            {'institution': self.institution.pk, 'exam': self.exam.pk},
        )

    def test_report_lists_student_identity_marks_total_and_total_based_merit(self):
        response = self._report()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Student ID')
        self.assertContains(response, 'SP001')
        self.assertContains(response, 'Candidate Three')
        self.assertContains(response, '80')
        self.assertEqual(
            [row['special_rank'] for row in response.context['report']['results']],
            [1, 1, 3],
        )
        self.assertEqual(
            [row['student'].pk for row in response.context['report']['results'][:2]],
            [self.roll_one.pk, self.roll_three.pk],
        )

    def test_manual_order_breaks_only_equal_total_and_recalculates_ranks(self):
        # Default register order is roll 1 then roll 3. Move roll 3 ahead.
        response = self.client.post(
            reverse('correct_special_exam_tie_order', args=[self.exam.pk]),
            {
                'total_marks': '80.00',
                'student_ids': f'{self.roll_three.pk},{self.roll_one.pk}',
                'group': '',
                'institution': str(self.institution.pk),
                'admission_class': '6',
                'session': '2026',
                'exam': str(self.exam.pk),
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            list(SpecialExamRankOrder.objects.filter(
                exam=self.exam, total_marks=80,
            ).order_by('order').values_list('student_id', flat=True)),
            [self.roll_three.pk, self.roll_one.pk],
        )

        report = self._report()
        rows = report.context['report']['results']
        self.assertEqual(
            [(row['student'].pk, row['special_rank']) for row in rows],
            [
                (self.roll_three.pk, 1),
                (self.roll_one.pk, 2),
                (self.roll_two.pk, 3),
            ],
        )

    def test_changed_marks_are_reflected_and_inapplicable_saved_tie_order_is_ignored(self):
        SpecialExamRankOrder.objects.create(
            exam=self.exam, student=self.roll_three, total_marks=80,
            order=1,
        )
        SpecialExamRankOrder.objects.create(
            exam=self.exam, student=self.roll_one, total_marks=80,
            order=2,
        )
        ExamMark.objects.filter(
            exam=self.exam, student=self.roll_three, subject=self.subject,
        ).update(marks_obtained=65)

        response = self._report()
        rows = response.context['report']['results']
        self.assertEqual(
            [(row['student'].student_id, row['total_obtained'], row['special_rank'])
             for row in rows],
            [
                ('SP001', 80, 1),
                ('SP002', 70, 2),
                ('SP003', 65, 3),
            ],
        )

    def test_invalid_partial_tie_order_is_rejected(self):
        response = self.client.post(
            reverse('correct_special_exam_tie_order', args=[self.exam.pk]),
            {'total_marks': '80', 'student_ids': str(self.roll_one.pk), 'group': ''},
            follow=True,
        )
        self.assertContains(response, 'Ordering can only be changed')
        self.assertFalse(SpecialExamRankOrder.objects.exists())

    def test_unenabled_and_non_special_exams_are_not_in_report_filter(self):
        self.exam.special_result_enabled = False
        self.exam.save(update_fields=['special_result_enabled'])
        response = self.client.get(
            reverse('special_exam_result_list'), {'exam': self.exam.pk},
        )
        self.assertIsNone(response.context['selected_exam'])

    def test_institution_class_and_session_filters_limit_available_exams(self):
        other_exam = Exam.objects.create(
            name='Special Exam Examination-2025',
            exam_type='SPECIAL_EXAM',
            institution=self.institution,
            admission_class='7',
            session='2025',
            is_published=True,
            special_result_enabled=True,
        )
        response = self.client.get(
            reverse('special_exam_result_list'),
            {
                'institution': self.institution.pk,
                'admission_class': '7',
                'session': '2025',
                'exam': other_exam.pk,
            },
        )
        self.assertEqual(response.context['selected_exam'], other_exam)
        self.assertEqual(list(response.context['exams']), [other_exam])

    def test_institution_bound_user_cannot_filter_into_another_school(self):
        other = Institution.objects.create(name='Other School', classes='6')
        other_exam = Exam.objects.create(
            name='Other Special Exam',
            exam_type='SPECIAL_EXAM',
            institution=other,
            admission_class='6',
            session='2026',
            is_published=True,
            special_result_enabled=True,
        )
        InstitutionAccess.objects.create(
            user=self.user, institution=self.institution, department='Exam',
        )
        response = self.client.get(
            reverse('special_exam_result_list'),
            {'institution': other.pk, 'exam': other_exam.pk},
        )
        self.assertIsNone(response.context['selected_exam'])
        self.assertNotContains(response, 'Other Special Exam')

    def test_special_result_setting_is_only_valid_for_special_exam_type(self):
        form_data = {
            'institution': self.institution.pk,
            'admission_class': '6',
            'section': '',
            'group': '',
            'exam_type': 'FIRST_TERM',
            'session': '2026',
            'exam_date': '',
            'is_published': '',
            'special_result_enabled': 'on',
        }
        form = ExamForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('special_result_enabled', form.errors)
