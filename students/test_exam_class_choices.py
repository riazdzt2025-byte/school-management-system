"""Tests for P1-6 (exam class choices beyond 1-12) and P1-8 (zero-padding)."""
from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase

from .forms import ExamForm
from .models import Exam, ExamMark, Institution, Student, Subject
from .views import save_student_subject_choices


class ExamClassChoiceTests(TestCase):
    def setUp(self):
        self.institution = Institution.objects.create(
            name='Shishu School', classes='Shishu,Nursery,1,2,9',
        )
        self.user = get_user_model().objects.create_user(
            username='staff', password='password',
        )

    def test_class_choices_come_from_institution(self):
        form = ExamForm(data={
            'institution': self.institution.pk, 'admission_class': 'Shishu',
            'section': '', 'group': '', 'exam_type': 'TEST_EXAM',
            'session': '2026', 'exam_date': '2026-01-01',
        }, user=self.user)
        codes = [code for code, _ in form.fields['admission_class'].choices]
        # Server-side must accept the institution's non-standard classes.
        self.assertIn('Shishu', codes)
        self.assertIn('Nursery', codes)
        self.assertIn('9', codes)
        self.assertTrue(form.is_valid(), form.errors)

    def test_student_class_choice_label_without_class_prefix(self):
        form = ExamForm(data={
            'institution': self.institution.pk, 'admission_class': 'Shishu',
            'section': '', 'group': '', 'exam_type': 'TEST_EXAM',
            'session': '2026', 'exam_date': '2026-01-01',
        }, user=self.user)
        labels = {code: label for code, label in form.fields['admission_class'].choices}
        self.assertEqual(labels['Shishu'], 'Shishu')
        self.assertEqual(labels['9'], 'Class 9')


class ZeroPaddingToleranceTests(TestCase):
    def setUp(self):
        self.institution = Institution.objects.create(
            name='School', classes='9,09',
        )
        self.subject = Subject.objects.create(
            code='BAN', name='Bangla', full_marks=100,
        )
        from .models import SubjectRequirement
        # Requirement stored with a non-padded '9'; the student is stored '09'.
        self.req = SubjectRequirement.objects.create(
            institution=self.institution, subject=self.subject,
            admission_class='9', requirement_type='MANDATORY',
        )

    def test_zero_padded_student_matches_non_padded_requirement(self):
        student = Student.objects.create(
            institution=self.institution, student_id='S001', name='Student One',
            admission_class='09', section='A', admission_year=2026, roll_no=1,
            gender='M', religion='Islam',
        )
        save_student_subject_choices(student, [self.req.pk])
        from .models import StudentSubjectChoice
        self.assertTrue(StudentSubjectChoice.objects.filter(
            student=student, requirement=self.req).exists())
