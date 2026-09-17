"""Audit trail read isolation (SEC session-02).

An audit row narrates what happened to a student/exam/application row, and
those rows are read-side isolated per institution. The audit trail must follow
the same rule: a user bound to Institution A who legitimately holds
``view_auditlog`` must not read Institution B's audit history from the list or
by guessing a pk. Rows with no institution (system-level actions and
everything recorded before the column existed) stay admin/staff-only
(deny-by-default, same rule as null-institution vouchers). The authorized
cross-institution administrator keeps full access.
"""
from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import reverse

from .audit import _audit_institution_for, record_audit
from .models import (
    AuditLog, AdmissionApplication, Employee, Exam, Institution, InstitutionAccess,
    MoneyReceipt, Student,
)


class AuditLogDerivationTests(TestCase):
    """record_audit fills the institution column from the audited object."""

    def setUp(self):
        self.institution = Institution.objects.create(name='Audit A', classes='6')
        self.user = get_user_model().objects.create_user(username='aud-unit', password='x')
        self.student = Student.objects.create(
            institution=self.institution, student_id='AU001', name='Audit Student',
            admission_class='6', section='A', admission_year=2026,
        )

    def test_object_with_institution_field(self):
        log = record_audit(self.user, 'student_archived', self.student)
        self.assertEqual(log.institution, self.institution)

    def test_object_resolved_through_student_link(self):
        receipt = MoneyReceipt.objects.create(
            student=self.student, receipt_no='RC-A1', purpose='Fee',
            amount=100, date=date(2026, 1, 1),
        )
        log = record_audit(self.user, 'payment_approved', receipt)
        self.assertEqual(log.institution, self.institution)

    def test_object_resolved_through_employee_link(self):
        employee = Employee.objects.create(
            institution=self.institution, name='Audit Employee',
            designation='Teacher', join_date=date(2026, 1, 1),
        )
        self.assertEqual(_audit_institution_for(employee), self.institution)

    def test_model_class_logs_have_no_institution_and_no_bogus_object_id(self):
        """Aggregates logged as record_audit(user, action, Student, ...) carry
        no pk-derived object_id (previously the string of the pk descriptor)."""
        log = record_audit(self.user, 'attendance_marked', Student, details={'count': 3})
        self.assertIsNone(log.institution)
        self.assertEqual(log.object_id, '')
        self.assertIn('student', log.object_repr)

    def test_no_instance_stays_null(self):
        log = record_audit(self.user, 'auto_registration', None, model_name='students.Student')
        self.assertIsNone(log.institution)


class AuditLogReadIsolationTests(TestCase):
    """A user with InstitutionAccess + view_auditlog reads only their own
    institutions' audit rows; NULL-institution rows are admin/staff-only."""

    def setUp(self):
        self.institution = Institution.objects.create(name='AuditLog A', classes='6')
        self.other = Institution.objects.create(name='AuditLog B', classes='6')

        self.clerk = get_user_model().objects.create_user(username='aud_clerk', password='x')
        InstitutionAccess.objects.create(
            user=self.clerk, institution=self.institution, department='Office',
        )
        self.clerk.user_permissions.add(
            Permission.objects.get(
                content_type=ContentType.objects.get_for_model(AuditLog),
                codename='view_auditlog',
            )
        )
        self.admin = get_user_model().objects.create_superuser(
            username='aud-admin', password='x', email='aud@example.com',
        )

        student_a = Student.objects.create(
            institution=self.institution, student_id='ALA001', name='Log Alpha',
            admission_class='6', section='A', admission_year=2026,
        )
        student_b = Student.objects.create(
            institution=self.other, student_id='ALB001', name='Log Beta',
            admission_class='6', section='A', admission_year=2026,
        )
        exam_b = Exam.objects.create(
            name='B Exam', exam_type='FIRST_TERM', institution=self.other,
            admission_class='6', section='', session='2026',
        )
        self.log_a = record_audit(self.admin, 'student_archived', student_a)
        self.log_b = record_audit(self.admin, 'exam_published', exam_b)
        # A legacy/system row: no institution (as everything logged before the
        # column existed, and as system actions still record).
        self.log_system = record_audit(
            self.admin, 'attendance_marked', Student,
            details={'count': 5, 'date': '2026-01-01'},
        )

    def login_as_clerk(self):
        self.client.force_login(self.clerk)
        session = self.client.session
        session['selected_institution_id'] = str(self.institution.pk)
        session['selected_department'] = 'Office'
        session.save()

    def test_list_shows_only_own_institution_rows(self):
        self.login_as_clerk()
        response = self.client.get(reverse('audit_log_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Log Alpha')
        self.assertNotContains(response, 'exam_published')
        self.assertNotContains(response, 'attendance_marked')

    def test_detail_404_for_other_institution_row(self):
        self.login_as_clerk()
        response = self.client.get(reverse('audit_log_detail', args=[self.log_b.pk]))
        self.assertEqual(response.status_code, 404)

    def test_detail_404_for_unscoped_row(self):
        self.login_as_clerk()
        response = self.client.get(reverse('audit_log_detail', args=[self.log_system.pk]))
        self.assertEqual(response.status_code, 404)

    def test_detail_ok_for_own_institution_row(self):
        self.login_as_clerk()
        response = self.client.get(reverse('audit_log_detail', args=[self.log_a.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Log Alpha')

    def test_admin_sees_everything_including_unscoped_rows(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('audit_log_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Log Alpha')
        self.assertContains(response, 'exam_published')
        self.assertContains(response, 'attendance_marked')

    def test_deactivated_access_row_cannot_log_in(self):
        """The production rule behind the unrestricted fallback: a user with no
        ACTIVE InstitutionAccess row has no way to obtain a session at all, so
        the legacy "no access row -> unrestricted" path can never serve a
        scoped clerk whose access was switched off."""
        InstitutionAccess.objects.filter(user=self.clerk).update(is_active=False)
        self.clerk.set_password('correct-password')
        self.clerk.save()
        response = self.client.post(reverse('login'), {
            'username': 'aud_clerk', 'password': 'correct-password',
            'institution_id': str(self.institution.pk), 'department': 'Office',
        })
        self.assertEqual(response.status_code, 200)  # back to the login form, not dashboard
        # No session was created: the next request to a login-required page
        # redirects to login instead of serving data.
        follow_up = self.client.get(reverse('audit_log_list'))
        self.assertEqual(follow_up.status_code, 302)
        self.assertIn(reverse('login'), follow_up.url)
