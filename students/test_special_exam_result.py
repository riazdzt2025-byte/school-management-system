from io import BytesIO

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
            exam_type='FIRST_TERM',
            institution=self.institution,
            admission_class='6',
            session='2026',
            is_published=True,
            is_special=True,
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
        self.exam.special_students.set([
            self.roll_one, self.roll_two, self.roll_three,
        ])
        self.exam.special_subjects.set([self.subject])
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
        self.assertContains(response, 'Special Exam Examination-2026')
        self.assertContains(response, 'First Term')
        self.assertContains(response, 'SP001')
        self.assertContains(response, 'Candidate Three')
        self.assertContains(response, '80')
        self.assertEqual(
            [row['special_rank'] for row in response.context['report']['results']],
            [1, 3, 1],
        )
        self.assertEqual(
            [row['student'].pk for row in response.context['report']['results']],
            [self.roll_one.pk, self.roll_two.pk, self.roll_three.pk],
        )
        self.assertEqual(
            [row['special_serial'] for row in response.context['report']['results']],
            [1, 3, 2],
        )
        self.assertLess(
            response.content.index(b'Total Marks'),
            response.content.index(b'Merit Rank'),
        )

    def test_merit_order_option_sorts_rows_by_rank(self):
        response = self.client.get(
            reverse('special_exam_result_list'),
            {'institution': self.institution.pk, 'exam': self.exam.pk, 'order': 'merit'},
        )
        self.assertEqual(
            [row['student'].pk for row in response.context['report']['results']],
            [self.roll_one.pk, self.roll_three.pk, self.roll_two.pk],
        )
        self.assertContains(response, 'value="merit" selected')

    def test_failing_subject_mark_is_highlighted_without_overall_result_column(self):
        ExamMark.objects.filter(
            exam=self.exam, student=self.roll_one, subject=self.subject,
        ).update(marks_obtained=40)
        ExamMark.objects.filter(
            exam=self.exam, student=self.roll_two, subject=self.subject,
        ).update(marks_obtained=20)

        response = self._report()
        rows = {
            row['student'].pk: row
            for row in response.context['report']['results']
        }
        self.assertEqual(rows[self.roll_one.pk]['total_full'], 100)
        self.assertEqual(rows[self.roll_two.pk]['total_full'], 100)
        self.assertEqual(rows[self.roll_two.pk]['subject_marks'], [20])
        self.assertTrue(rows[self.roll_two.pk]['subject_mark_details'][0]['failed'])
        self.assertEqual(rows[self.roll_two.pk]['status'], 'Fail')
        self.assertNotIn('result_status', rows[self.roll_two.pk])
        self.assertContains(response, 'A+ Count')
        self.assertContains(response, '<span class="special-failing-mark">20</span>', html=True)
        self.assertNotContains(response, 'Result (40%)')
        self.assertNotContains(response, 'special-result-box')

        # Existing merit ranks and register-roll display order remain unchanged.
        self.assertEqual(
            [row['student'].pk for row in response.context['report']['results']],
            [self.roll_one.pk, self.roll_two.pk, self.roll_three.pk],
        )
        self.assertEqual(
            [row['special_rank'] for row in response.context['report']['results']],
            [2, 0, 1],
        )
        self.assertEqual(
            [row['special_serial'] for row in response.context['report']['results']],
            [2, 3, 1],
        )
        self.assertContains(response, '<td class="text-center fw-bold">0</td>', html=True)

    def test_only_passed_students_advance_merit_positions(self):
        ExamMark.objects.filter(
            exam=self.exam, student=self.roll_two, subject=self.subject,
        ).update(marks_obtained=20)
        ExamMark.objects.filter(
            exam=self.exam, student=self.roll_three, subject=self.subject,
        ).update(marks_obtained=30)

        response = self.client.get(
            reverse('special_exam_result_list'),
            {
                'institution': self.institution.pk,
                'exam': self.exam.pk,
                'order': 'merit',
            },
        )
        rows = response.context['report']['results']
        self.assertEqual(
            [
                (row['student'].pk, row['special_serial'], row['special_rank'])
                for row in rows
            ],
            [
                (self.roll_one.pk, 1, 1),
                (self.roll_three.pk, 2, 0),
                (self.roll_two.pk, 3, 0),
            ],
        )

    def test_zero_merit_students_follow_passed_students_in_total_order(self):
        second_subject = Subject.objects.create(
            code='SCI', name='Science', full_marks=100,
        )
        SubjectRequirement.objects.create(
            institution=self.institution, admission_class='6',
            subject=second_subject, requirement_type='MANDATORY',
        )
        self.exam.special_subjects.add(second_subject)
        ExamMark.objects.filter(
            exam=self.exam, student=self.roll_one, subject=self.subject,
        ).update(marks_obtained=40)
        ExamMark.objects.filter(
            exam=self.exam, student=self.roll_two, subject=self.subject,
        ).update(marks_obtained=20)
        ExamMark.objects.filter(
            exam=self.exam, student=self.roll_three, subject=self.subject,
        ).update(marks_obtained=40)
        for student, marks in (
            (self.roll_one, 40), (self.roll_two, 100), (self.roll_three, 40),
        ):
            ExamMark.objects.create(
                exam=self.exam, student=student, subject=second_subject,
                marks_obtained=marks,
            )

        response = self.client.get(
            reverse('special_exam_result_list'),
            {
                'institution': self.institution.pk,
                'exam': self.exam.pk,
                'order': 'merit',
            },
        )
        rows = response.context['report']['results']
        self.assertEqual(
            [row['student'].pk for row in rows],
            [self.roll_one.pk, self.roll_three.pk, self.roll_two.pk],
        )
        self.assertEqual(
            [(row['total_obtained'], row['special_rank']) for row in rows],
            [(80, 1), (80, 1), (120, 0)],
        )

    def test_a_plus_count_counts_subject_grades_and_absence_is_not_a_display_mark(self):
        response = self._report()
        rows = {
            row['student'].pk: row
            for row in response.context['report']['results']
        }
        self.assertEqual(rows[self.roll_one.pk]['a_plus_count'], 1)
        self.assertEqual(rows[self.roll_two.pk]['a_plus_count'], 0)
        self.assertEqual(rows[self.roll_three.pk]['a_plus_count'], 1)

        unmarked = Student.objects.create(
            institution=self.institution, student_id='SP004',
            name='Candidate Four', admission_class='6', roll_no=4,
        )
        self.exam.special_students.add(unmarked)

        response = self._report()
        row = next(
            row for row in response.context['report']['results']
            if row['student'].pk == unmarked.pk
        )
        self.assertEqual(row['subject_marks'], [None])
        self.assertFalse(row['subject_mark_details'][0]['failed'])
        self.assertEqual(row['a_plus_count'], 0)

    def test_excel_exports_preserve_both_row_orders_and_column_order(self):
        from openpyxl import load_workbook

        url = reverse('download_special_exam_result', args=[self.exam.pk])
        orders = (
            ('roll', [self.roll_one.student_id, self.roll_two.student_id, self.roll_three.student_id]),
            ('merit', [self.roll_one.student_id, self.roll_three.student_id, self.roll_two.student_id]),
        )
        for order, expected_students in orders:
            with self.subTest(order=order):
                response = self.client.get(url, {
                    'institution': self.institution.pk,
                    'admission_class': '6',
                    'session': '2026',
                    'exam': self.exam.pk,
                    'order': order,
                })
                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    response['Content-Type'],
                    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                )
                sheet = load_workbook(BytesIO(response.content), data_only=True).active
                headers = [cell.value for cell in sheet[1]]
                self.assertEqual(
                    headers,
                    [
                        'Serial', 'Roll', 'Student ID', 'Student Name', 'English',
                        'Total Marks', 'A+ Count', 'Merit Rank',
                    ],
                )
                self.assertEqual(
                    [sheet.cell(row=row, column=3).value for row in range(2, 5)],
                    expected_students,
                )
                self.assertEqual(
                    [sheet.cell(row=row, column=7).value for row in range(2, 5)],
                    [1, 0, 1] if order == 'roll' else [1, 1, 0],
                )
                self.assertEqual(
                    [sheet.cell(row=row, column=1).value for row in range(2, 5)],
                    [1, 3, 2] if order == 'roll' else [1, 2, 3],
                )

    def test_excel_export_marks_failing_subject_cells_black(self):
        from openpyxl import load_workbook

        ExamMark.objects.filter(
            exam=self.exam, student=self.roll_two, subject=self.subject,
        ).update(marks_obtained=20)
        response = self.client.get(
            reverse('download_special_exam_result', args=[self.exam.pk]),
            {'institution': self.institution.pk},
        )
        sheet = load_workbook(BytesIO(response.content), data_only=False).active
        failing_mark = sheet.cell(row=3, column=5)
        self.assertEqual(failing_mark.value, 20)
        self.assertEqual(failing_mark.fill.fgColor.rgb[-6:], '000000')
        self.assertEqual(failing_mark.font.color.rgb[-6:], 'FFFFFF')

    def test_excel_export_respects_institution_access(self):
        other = Institution.objects.create(name='Other School', classes='6')
        other_exam = Exam.objects.create(
            name='Other Special Exam',
            exam_type='FIRST_TERM',
            institution=other,
            admission_class='6',
            session='2026',
            is_published=True,
            is_special=True,
            special_result_enabled=True,
        )
        InstitutionAccess.objects.create(
            user=self.user, institution=self.institution, department='Exam',
        )
        response = self.client.get(
            reverse('download_special_exam_result', args=[other_exam.pk]),
        )
        self.assertEqual(response.status_code, 404)

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
                (self.roll_one.pk, 2),
                (self.roll_two.pk, 3),
                (self.roll_three.pk, 1),
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
            exam_type='FIRST_TERM',
            institution=self.institution,
            admission_class='7',
            session='2025',
            is_published=True,
            is_special=True,
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
            exam_type='FIRST_TERM',
            institution=other,
            admission_class='6',
            session='2026',
            is_published=True,
            is_special=True,
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

    def test_special_result_setting_is_cleared_for_regular_exams(self):
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
        self.assertTrue(form.is_valid(), form.errors)
        self.assertFalse(form.cleaned_data['special_result_enabled'])
