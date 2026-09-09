"""Tests for P1-5: the student-detail 'Subjects & Curriculum' tab shows current
SubjectRequirement-derived assignments (and the student's chosen optional),
instead of the legacy admin-only StudentSubject rows.
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from .models import Institution, Student, StudentSubjectChoice, Subject, SubjectRequirement
from .views import save_student_subject_choices


class CurriculumTabTests(TestCase):
    def setUp(self):
        self.institution = Institution.objects.create(name='School', classes='6')
        self.user = get_user_model().objects.create_user(
            username='office', password='password',
        )
        self.user.user_permissions.add(
            Permission.objects.get(codename='view_student')
        )
        self.student = Student.objects.create(
            institution=self.institution, student_id='S001', name='Student One',
            admission_class='6', section='A', admission_year=2026, roll_no=1,
            gender='M', religion='Islam',
        )
        self.mand = Subject.objects.create(
            code='BAN', name='Bangla', full_marks=100, category='COMPULSORY',
        )
        self.opt = Subject.objects.create(
            code='HIS', name='History', full_marks=100, category='OPTIONAL',
        )
        self.req_mand = SubjectRequirement.objects.create(
            institution=self.institution, subject=self.mand,
            admission_class='6', requirement_type='MANDATORY',
        )
        self.req_opt = SubjectRequirement.objects.create(
            institution=self.institution, subject=self.opt,
            admission_class='6', requirement_type='OPTIONAL',
            optional_set_key='social',
        )

    def test_detail_shows_mandatory_and_chosen_optional(self):
        # The student chose the optional History subject.
        save_student_subject_choices(self.student, [self.req_opt.pk])
        self.client.force_login(self.user)
        response = self.client.get(reverse('student_detail', args=[self.student.pk]))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn('Bangla', body)
        self.assertIn('History', body)
        self.assertIn('Mandatory', body)
        self.assertIn('Chosen', body)
        # No legacy curriculum column names leak.
        self.assertNotIn('is_discontinued', body)

    def test_unchosen_optional_shows_not_chosen(self):
        # No choice saved for the optional subject.
        self.client.force_login(self.user)
        response = self.client.get(reverse('student_detail', args=[self.student.pk]))
        body = response.content.decode()
        self.assertIn('History', body)
        self.assertIn('Not chosen', body)
