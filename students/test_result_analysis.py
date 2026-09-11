"""Regression coverage for Result Analysis and SSC Science curriculum rules."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from django.urls import resolve, reverse

from .curriculum_data import HSC_GROUPS, SSC_GROUPS, curriculum_for_class
from .models import (
    AuditLog, Exam, ExamMark, Institution, InstitutionAccess, SectionCapacity,
    Student, Subject, SubjectRequirement,
)
from .result_utils import failed_subject_rows, section_arrangement_rows


class ResultAnalysisFixture(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.institution = Institution.objects.create(name='Test School', classes='9,10,11')
        cls.other_institution = Institution.objects.create(name='Other School', classes='9')
        cls.user = get_user_model().objects.create_superuser('admin', 'a@example.com', 'password')
        cls.subject = Subject.objects.create(code='HMATH', name='Higher Mathematics', full_marks=100)
        cls.biology = Subject.objects.create(code='BIO', name='Biology', full_marks=100)
        SubjectRequirement.objects.create(
            institution=cls.institution, admission_class='9', group='SCI',
            subject=cls.subject, requirement_type='MANDATORY',
        )
        cls.first = Student.objects.create(
            institution=cls.institution, student_id='S1', form_no='1', name='First',
            admission_class='9', section='B', roll_no=1, group='SCI',
            guardian_contact_no='01800000001',
        )
        cls.second = Student.objects.create(
            institution=cls.institution, student_id='S2', form_no='2', name='Second',
            admission_class='09', section='A', roll_no=2, group='SCI',
            guardian_contact_no='01800000002',
        )
        cls.exam = Exam.objects.create(
            name='First Term', exam_type='FIRST_TERM', institution=cls.institution,
            admission_class='9', group='SCI', session='2026', is_published=True,
        )
        ExamMark.objects.create(exam=cls.exam, student=cls.first, subject=cls.subject, marks_obtained=80)
        ExamMark.objects.create(exam=cls.exam, student=cls.second, subject=cls.subject, marks_obtained=20)
        cls.exam2 = Exam.objects.create(
            name='Second Term', exam_type='SECOND_TERM', institution=cls.institution,
            admission_class='9', group='SCI', session='2026', is_published=True,
        )
        ExamMark.objects.create(exam=cls.exam2, student=cls.first, subject=cls.subject, marks_obtained=85)
        ExamMark.objects.create(exam=cls.exam2, student=cls.second, subject=cls.subject, marks_obtained=25)

    def setUp(self):
        self.client.force_login(self.user)


class CurriculumRuleTests(ResultAnalysisFixture):
    def test_ssc_higher_math_is_mandatory(self):
        self.assertIn(('HMATH', 'MANDATORY', '', ''), SSC_GROUPS['SCI'])

    def test_ssc_higher_math_is_not_optional(self):
        self.assertNotIn(('HMATH', 'OPTIONAL', 'sci_4th', ''), SSC_GROUPS['SCI'])

    def test_ssc_biology_remains_optional(self):
        self.assertIn(('BIO', 'OPTIONAL', 'sci_4th', ''), SSC_GROUPS['SCI'])

    def test_hsc_higher_math_remains_optional(self):
        self.assertIn(('HMATH', 'OPTIONAL', 'sci_4th', ''), HSC_GROUPS['SCI'])

    def test_hsc_biology_remains_optional(self):
        self.assertIn(('BIO', 'OPTIONAL', 'sci_4th', ''), HSC_GROUPS['SCI'])

    def test_business_curriculum_is_unchanged(self):
        self.assertIn(('ACC', 'MANDATORY', '', ''), SSC_GROUPS['BUS'])

    def test_class_nine_uses_ssc_rules(self):
        self.assertIs(curriculum_for_class('9')[1], SSC_GROUPS)


class AnalysisHelperTests(ResultAnalysisFixture):
    def test_failed_rows_contains_failed_student(self):
        self.assertEqual(failed_subject_rows(self.exam)[0]['student'], self.second)

    def test_failed_rows_excludes_passed_student(self):
        self.assertNotIn(self.first, [r['student'] for r in failed_subject_rows(self.exam)])

    def test_failed_rows_identifies_subject(self):
        self.assertEqual(failed_subject_rows(self.exam)[0]['subject'], self.subject)

    def test_failed_rows_includes_obtained_mark(self):
        self.assertEqual(failed_subject_rows(self.exam)[0]['obtained'], Decimal('20'))

    def test_failed_rows_are_institution_scoped(self):
        other = Student.objects.create(institution=self.other_institution, student_id='O1', name='Other', admission_class='9', group='SCI', guardian_contact_no='01800000003')
        ExamMark.objects.create(exam=self.exam, student=other, subject=self.subject, marks_obtained=0)
        self.assertNotIn(other, [r['student'] for r in failed_subject_rows(self.exam)])

    def test_arrangement_puts_fewer_fails_first(self):
        self.assertEqual(section_arrangement_rows(self.exam)[0]['student'], self.first)

    def test_arrangement_reports_failed_count(self):
        rows = section_arrangement_rows(self.exam)
        self.assertEqual(next(r for r in rows if r['student'] == self.second)['failed_subject_count'], 1)

    def test_arrangement_keeps_current_section_in_preview(self):
        self.assertEqual(section_arrangement_rows(self.exam)[0]['current_section'], 'B')

    def test_arrangement_does_not_mutate_student(self):
        section_arrangement_rows(self.exam)
        self.first.refresh_from_db()
        self.assertEqual(self.first.section, 'B')

    def test_arrangement_tie_uses_total_descending(self):
        ExamMark.objects.filter(exam=self.exam, student=self.second).update(marks_obtained=70)
        rows = section_arrangement_rows(self.exam)
        self.assertEqual([r['student'] for r in rows], [self.first, self.second])


class AnalysisRouteTests(ResultAnalysisFixture):
    ROUTES = [
        'result_analysis_subject_fail', 'result_analysis_multi_term',
        'result_analysis_merit_slides', 'result_analysis_result_cards',
        'section_arrangement',
    ]

    def test_subject_fail_route_resolves(self):
        self.assertEqual(resolve(reverse('result_analysis_subject_fail')).func.__name__, 'result_analysis_subject_fail')

    def test_multi_term_route_resolves(self):
        self.assertEqual(resolve(reverse('result_analysis_multi_term')).func.__name__, 'result_analysis_multi_term')

    def test_merit_slides_route_resolves(self):
        self.assertEqual(resolve(reverse('result_analysis_merit_slides')).func.__name__, 'result_analysis_merit_slides')

    def test_result_cards_route_resolves(self):
        self.assertEqual(resolve(reverse('result_analysis_result_cards')).func.__name__, 'result_analysis_result_cards')

    def test_section_arrangement_route_resolves(self):
        self.assertEqual(resolve(reverse('section_arrangement')).func.__name__, 'section_arrangement')

    def test_subject_fail_page_renders(self):
        response = self.client.get(reverse('result_analysis_subject_fail'), {'exam': self.exam.pk})
        self.assertContains(response, 'Second')

    def test_subject_fail_page_shows_subject(self):
        response = self.client.get(reverse('result_analysis_subject_fail'), {'exam': self.exam.pk})
        self.assertContains(response, 'Higher Mathematics')

    def test_merit_slides_only_show_top_three(self):
        response = self.client.get(reverse('result_analysis_merit_slides'), {'exam': self.exam.pk})
        self.assertEqual([row['student'] for row in response.context['top_three']], [self.first])

    def test_class_result_cards_show_marked_students(self):
        response = self.client.get(reverse('result_analysis_result_cards'), {'exam': self.exam.pk})
        self.assertContains(response, 'First')
        self.assertContains(response, 'Second')

    def test_multi_term_accepts_two_exams(self):
        response = self.client.get(reverse('result_analysis_multi_term'), {'exams': [self.exam.pk, self.exam2.pk]})
        self.assertEqual(len(response.context['selected_exams']), 2)

    def test_multi_term_rejects_one_exam(self):
        response = self.client.get(reverse('result_analysis_multi_term'), {'exams': [self.exam.pk]})
        self.assertFalse(response.context['selected_exams'])

    def test_unpublished_exam_is_not_selectable(self):
        self.exam.is_published = False
        self.exam.save(update_fields=['is_published'])
        response = self.client.get(reverse('result_analysis_subject_fail'))
        self.assertNotContains(response, 'First Term')

    def test_anonymous_user_is_redirected(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse('result_analysis_subject_fail')).status_code, 302)

    def test_accounts_only_user_is_forbidden(self):
        user = get_user_model().objects.create_user('accounts', password='password')
        InstitutionAccess.objects.create(user=user, institution=self.institution, department='Accounts')
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse('result_analysis_subject_fail')).status_code, 403)

    def test_other_institution_exam_is_hidden_from_scoped_user(self):
        user = get_user_model().objects.create_user('examclerk', password='password')
        InstitutionAccess.objects.create(user=user, institution=self.institution, department='Exam')
        self.client.force_login(user)
        other_exam = Exam.objects.create(name='Hidden', exam_type='FIRST_TERM', institution=self.other_institution, admission_class='9', session='2026', is_published=True)
        response = self.client.get(reverse('result_analysis_subject_fail'))
        self.assertNotContains(response, f'value="{other_exam.pk}"')


class SectionArrangementTests(ResultAnalysisFixture):
    def _preview_url(self):
        return reverse('section_arrangement') + f'?exam={self.exam.pk}&sections=A,B'

    def test_preview_does_not_save(self):
        self.client.get(self._preview_url())
        self.first.refresh_from_db()
        self.assertEqual(self.first.section, 'B')

    def test_confirm_changes_section_not_roll(self):
        SectionCapacity.objects.create(institution=self.institution, admission_class='9', section='A', capacity=1)
        SectionCapacity.objects.create(institution=self.institution, admission_class='9', section='B', capacity=1)
        response = self.client.post(reverse('section_arrangement'), {'exam': self.exam.pk, 'sections': 'A,B', 'action': 'confirm'})
        self.assertEqual(response.status_code, 302)
        self.first.refresh_from_db()
        self.assertEqual(self.first.roll_no, 1)
        self.assertEqual(self.first.section, 'A')

    def test_confirm_records_audit_log(self):
        self.client.post(reverse('section_arrangement'), {'exam': self.exam.pk, 'sections': 'A,B', 'action': 'confirm'})
        self.assertTrue(AuditLog.objects.filter(action='section_arrangement_confirmed').exists())

    def test_capacity_shortage_blocks_confirm(self):
        SectionCapacity.objects.create(institution=self.institution, admission_class='9', section='A', capacity=1)
        response = self.client.post(reverse('section_arrangement'), {'exam': self.exam.pk, 'sections': 'A', 'action': 'confirm'})
        self.assertEqual(response.status_code, 200)
        self.first.refresh_from_db()
        self.assertEqual(self.first.section, 'B')

    def test_page_displays_capacity_warning(self):
        SectionCapacity.objects.create(institution=self.institution, admission_class='9', section='A', capacity=1)
        response = self.client.get(self._preview_url().replace('A,B', 'A'))
        self.assertContains(response, 'SectionCapacity warning')

    def test_non_confirm_post_never_saves(self):
        response = self.client.post(reverse('section_arrangement'), {'exam': self.exam.pk, 'sections': 'A,B', 'action': 'preview'})
        self.assertEqual(response.status_code, 200)
        self.first.refresh_from_db()
        self.assertEqual(self.first.section, 'B')
