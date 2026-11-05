"""EM-01: teacher ↔ class/section/subject assignment registry.

Covers the model validation (class offered by the institution, subject in the
curriculum, employee in the same institution), the active-assignment
uniqueness rule, the permission gates, institution scoping, the audited
unassign flow, the employee-detail tab and the signature-sheet integration.
"""
from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from .models import (
    AuditLog, Employee, Exam, Institution, InstitutionAccess, SeatPlan, Student,
    Subject, SubjectRequirement, TeacherAssignment,
)
from .permissions import ensure_default_groups, sync_user_department_permissions


class TeacherAssignmentValidationTests(TestCase):
    def setUp(self):
        self.institution = Institution.objects.create(name='Assignment School', classes='9,10')
        self.other = Institution.objects.create(name='Other Assignment School', classes='9,10')
        self.employee = Employee.objects.create(
            institution=self.institution, name='Teacher One', designation='Assistant Teacher',
            join_date=date(2026, 1, 1),
        )
        self.other_employee = Employee.objects.create(
            institution=self.other, name='Other Teacher', designation='Teacher',
            join_date=date(2026, 1, 1),
        )
        self.subject = Subject.objects.create(code='PHY', name='Physics', full_marks=100)
        self.outside_subject = Subject.objects.create(code='XXX', name='Outside Subject', full_marks=100)
        SubjectRequirement.objects.create(
            institution=self.institution, admission_class='9', subject=self.subject,
        )
        ensure_default_groups()
        self.user = get_user_model().objects.create_user(username='assigner', password='password')
        self.user.user_permissions.add(Permission.objects.get(codename='add_teacherassignment'))
        self.user.user_permissions.add(Permission.objects.get(codename='view_teacherassignment'))
        self.client.force_login(self.user)

    def _post(self, **overrides):
        payload = {
            'institution': self.institution.pk,
            'employee': self.employee.pk,
            'admission_class': '9',
            'section': 'A',
            'subject': self.subject.pk,
            'session': '2026-2027',
            'is_active': 'on',
        }
        payload.update(overrides)
        return self.client.post(reverse('add_teacher_assignment'), payload)

    def test_valid_assignment_is_created_and_audited(self):
        response = self._post()
        self.assertRedirects(response, reverse('teacher_assignment_list'))
        self.assertEqual(TeacherAssignment.objects.count(), 1)
        log = AuditLog.objects.filter(action='teacher_assignment_created').last()
        self.assertIsNotNone(log)
        self.assertEqual(log.details['subject'], 'Physics')

    def test_duplicate_active_assignment_is_blocked(self):
        self._post()
        response = self._post()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(TeacherAssignment.objects.count(), 1)
        self.assertContains(response, 'already exists')

    def test_class_not_offered_by_institution_is_rejected(self):
        response = self._post(admission_class='8')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(TeacherAssignment.objects.count(), 0)

    def test_subject_outside_the_curriculum_is_rejected(self):
        response = self._post(subject=self.outside_subject.pk)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(TeacherAssignment.objects.count(), 0)
        self.assertContains(response, 'not part of the curriculum')

    def test_employee_from_another_institution_is_rejected(self):
        response = self._post(employee=self.other_employee.pk)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(TeacherAssignment.objects.count(), 0)

    def test_list_page_renders_assignment(self):
        self._post()
        response = self.client.get(reverse('teacher_assignment_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Teacher One')
        self.assertContains(response, 'Physics')

    def test_user_without_permission_is_forbidden(self):
        self.client.logout()
        plain = get_user_model().objects.create_user(username='plain-assign', password='password')
        self.client.force_login(plain)
        self.assertEqual(self.client.get(reverse('teacher_assignment_list')).status_code, 403)
        self.assertEqual(self.client.post(reverse('add_teacher_assignment'), {}).status_code, 403)


class TeacherAssignmentScopeAndIntegrationTests(TestCase):
    def setUp(self):
        self.institution = Institution.objects.create(name='Scope School', classes='9,10')
        self.other = Institution.objects.create(name='Other Scope School', classes='9,10')
        self.employee = Employee.objects.create(
            institution=self.institution, name='Scope Teacher', designation='Teacher',
            join_date=date(2026, 1, 1),
        )
        self.subject = Subject.objects.create(code='CHE', name='Chemistry', full_marks=100)
        SubjectRequirement.objects.create(
            institution=self.institution, admission_class='9', subject=self.subject,
        )
        self.assignment = TeacherAssignment.objects.create(
            institution=self.institution, employee=self.employee,
            admission_class='9', section='A', subject=self.subject, session='2026-2027',
        )
        self.student = Student.objects.create(
            institution=self.institution, student_id='TA001', name='Exam Student',
            admission_class='9', section='A', admission_year=2026, roll_no=1,
        )
        self.exam = Exam.objects.create(
            name='Mid Term', exam_type='MID_TERM_1', institution=self.institution,
            admission_class='9', section='A', session='2026-2027',
        )
        SeatPlan.objects.create(exam=self.exam, room_name='Room 1', student=self.student, seat_no=1)
        ensure_default_groups()
        self.other_user = get_user_model().objects.create_user(username='other-scope', password='password')
        InstitutionAccess.objects.create(
            user=self.other_user, institution=self.other, department='Office', is_active=True,
        )
        sync_user_department_permissions(self.other_user)
        self.client.force_login(self.other_user)

    def test_cross_institution_edit_is_404(self):
        response = self.client.get(reverse('edit_teacher_assignment', args=[self.assignment.pk]))
        self.assertEqual(response.status_code, 404)

    def test_cross_institution_toggle_is_404(self):
        response = self.client.post(reverse('toggle_teacher_assignment', args=[self.assignment.pk]))
        self.assertEqual(response.status_code, 404)
        self.assignment.refresh_from_db()
        self.assertTrue(self.assignment.is_active)

    def test_signature_sheet_shows_assigned_teacher(self):
        self.client.logout()
        admin = get_user_model().objects.create_superuser(username='sig-admin', password='password')
        self.client.force_login(admin)
        response = self.client.get(reverse('signature_sheet', args=[self.exam.pk, 'Room 1']))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Scope Teacher')
        self.assertContains(response, 'Chemistry')

    def test_unassign_removes_teacher_from_signature_sheet(self):
        self.client.logout()
        admin = get_user_model().objects.create_superuser(username='sig-admin-2', password='password')
        self.client.force_login(admin)
        response = self.client.post(reverse('toggle_teacher_assignment', args=[self.assignment.pk]))
        self.assertRedirects(response, reverse('teacher_assignment_list'))
        self.assignment.refresh_from_db()
        self.assertFalse(self.assignment.is_active)
        log = AuditLog.objects.filter(action='teacher_assignment_toggled').last()
        self.assertIsNotNone(log)
        self.assertFalse(log.details['is_active'])
        sheet = self.client.get(reverse('signature_sheet', args=[self.exam.pk, 'Room 1']))
        self.assertNotContains(sheet, 'Scope Teacher')

    def test_employee_detail_shows_assignment_tab(self):
        self.client.logout()
        admin = get_user_model().objects.create_superuser(username='emp-admin', password='password')
        self.client.force_login(admin)
        response = self.client.get(reverse('employee_detail', args=[self.employee.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Assignments')
        self.assertContains(response, 'Chemistry')
