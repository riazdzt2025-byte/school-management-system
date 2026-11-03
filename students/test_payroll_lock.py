"""EM-03: closed-period lock for salary sheets.

A locked sheet is frozen: edit and delete are refused, the lock/unlock
actions are audited, and the lock is scoped to the employee's institution.
"""
from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from .models import AuditLog, Employee, Institution, InstitutionAccess, SalarySheet
from .permissions import ensure_default_groups, sync_user_department_permissions


class SalarySheetLockTests(TestCase):
    def setUp(self):
        self.institution = Institution.objects.create(name='Payroll School', classes='6')
        self.other = Institution.objects.create(name='Other Payroll School', classes='6')
        self.employee = Employee.objects.create(
            institution=self.institution, name='Payroll Teacher', designation='Teacher',
            join_date=date(2026, 1, 1),
        )
        self.other_employee = Employee.objects.create(
            institution=self.other, name='Other Payroll Teacher', designation='Teacher',
            join_date=date(2026, 1, 1),
        )
        self.salary = SalarySheet.objects.create(
            employee=self.employee, month='January 2026', amount='25000.00',
            date=date(2026, 1, 31), status='PAID',
        )
        self.other_salary = SalarySheet.objects.create(
            employee=self.other_employee, month='January 2026', amount='30000.00',
            date=date(2026, 1, 31), status='UNPAID',
        )
        ensure_default_groups()
        self.user = get_user_model().objects.create_user(username='accounts-clerk', password='password')
        self.user.user_permissions.add(Permission.objects.get(codename='change_salarysheet'))
        self.user.user_permissions.add(Permission.objects.get(codename='delete_salarysheet'))
        self.client.force_login(self.user)

    def test_lock_freezes_the_sheet_and_is_audited(self):
        response = self.client.post(reverse('lock_salary_sheet', args=[self.salary.pk]), {'reason': 'January closed'})
        self.assertRedirects(response, reverse('salary_sheet_list'))
        self.salary.refresh_from_db()
        self.assertIsNotNone(self.salary.locked_at)
        self.assertEqual(self.salary.locked_by, self.user)
        self.assertEqual(self.salary.lock_reason, 'January closed')
        log = AuditLog.objects.filter(action='salary_sheet_locked').last()
        self.assertIsNotNone(log)

    def test_locked_sheet_cannot_be_edited(self):
        self.client.post(reverse('lock_salary_sheet', args=[self.salary.pk]))
        response = self.client.post(reverse('edit_salary_sheet', args=[self.salary.pk]), {
            'employee': self.employee.pk, 'month': 'January 2026',
            'amount': '1.00', 'date': '2026-01-31', 'status': 'UNPAID',
        })
        self.assertRedirects(response, reverse('salary_sheet_list'))
        self.salary.refresh_from_db()
        self.assertEqual(self.salary.amount, 25000)
        self.assertEqual(self.salary.status, 'PAID')

    def test_locked_sheet_cannot_be_deleted(self):
        self.client.post(reverse('lock_salary_sheet', args=[self.salary.pk]))
        response = self.client.post(reverse('delete_salary_sheet', args=[self.salary.pk]))
        self.assertRedirects(response, reverse('salary_sheet_list'))
        self.assertTrue(SalarySheet.objects.filter(pk=self.salary.pk).exists())

    def test_unlock_restores_editing_and_is_audited(self):
        self.client.post(reverse('lock_salary_sheet', args=[self.salary.pk]))
        response = self.client.post(reverse('unlock_salary_sheet', args=[self.salary.pk]))
        self.assertRedirects(response, reverse('salary_sheet_list'))
        self.salary.refresh_from_db()
        self.assertIsNone(self.salary.locked_at)
        self.assertIsNone(self.salary.locked_by)
        log = AuditLog.objects.filter(action='salary_sheet_unlocked').last()
        self.assertIsNotNone(log)
        edit = self.client.post(reverse('edit_salary_sheet', args=[self.salary.pk]), {
            'employee': self.employee.pk, 'month': 'January 2026',
            'amount': '26000.00', 'date': '2026-01-31', 'status': 'PAID',
        })
        self.assertRedirects(edit, reverse('salary_sheet_list'))
        self.salary.refresh_from_db()
        self.assertEqual(self.salary.amount, 26000)

    def test_lock_is_idempotent(self):
        self.client.post(reverse('lock_salary_sheet', args=[self.salary.pk]))
        self.salary.refresh_from_db()
        first = self.salary.locked_at
        self.client.post(reverse('lock_salary_sheet', args=[self.salary.pk]))
        self.salary.refresh_from_db()
        self.assertEqual(self.salary.locked_at, first)

    def test_cross_institution_lock_is_404(self):
        self.client.logout()
        other_user = get_user_model().objects.create_user(username='other-payroll', password='password')
        InstitutionAccess.objects.create(
            user=other_user, institution=self.other, department='Accounts', is_active=True,
        )
        sync_user_department_permissions(other_user)
        self.client.force_login(other_user)
        response = self.client.post(reverse('lock_salary_sheet', args=[self.salary.pk]))
        self.assertEqual(response.status_code, 404)
        self.salary.refresh_from_db()
        self.assertIsNone(self.salary.locked_at)

    def test_list_shows_lock_state_and_actions(self):
        self.client.post(reverse('lock_salary_sheet', args=[self.salary.pk]))
        response = self.client.get(reverse('salary_sheet_list'))
        self.assertContains(response, 'Locked')
        self.assertContains(response, 'Unlock')
