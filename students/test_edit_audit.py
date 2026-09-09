"""Tests for P2-4: audit entries on edit_student / edit_employee field changes."""
from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from .models import AuditLog, Employee, Institution, Student


class EditAuditTests(TestCase):
    def setUp(self):
        self.institution = Institution.objects.create(name='School', classes='6')
        self.user = get_user_model().objects.create_user(
            username='office', password='password',
        )
        for codename in ['change_student', 'change_employee']:
            self.user.user_permissions.add(Permission.objects.get(codename=codename))
        self.client.force_login(self.user)
        self.student = Student.objects.create(
            institution=self.institution, student_id='S001', name='Student One',
            admission_class='6', section='A', admission_year=2026, roll_no=1,
            gender='M', religion='Islam',
        )
        self.employee = Employee.objects.create(
            institution=self.institution, name='Emp One', designation='Teacher',
            join_date=date(2026, 1, 1),
        )

    def test_edit_student_writes_audit(self):
        response = self.client.post(reverse('edit_student', args=[self.student.pk]), {
            'institution': self.institution.pk, 'name': 'Renamed One',
            'admission_class': '6', 'section': 'A', 'admission_year': 2026,
            'roll_no': 1, 'gender': 'M', 'religion': 'Islam', 'status': 'ACTIVE',
        })
        self.assertEqual(response.status_code, 302)
        log = AuditLog.objects.filter(action='student_updated').last()
        self.assertIsNotNone(log)
        self.assertEqual(log.object_id, str(self.student.pk))
        self.assertIn('name', log.details['changed_fields'])

    def test_edit_employee_writes_audit(self):
        response = self.client.post(reverse('edit_employee', args=[self.employee.pk]), {
            'institution': self.institution.pk, 'name': 'Emp Renamed',
            'designation': 'Head Teacher', 'join_date': '2026-01-01',
        })
        self.assertEqual(response.status_code, 302)
        log = AuditLog.objects.filter(action='employee_updated').last()
        self.assertIsNotNone(log)
        self.assertEqual(log.object_id, str(self.employee.pk))
        self.assertIn('designation', log.details['changed_fields'])
