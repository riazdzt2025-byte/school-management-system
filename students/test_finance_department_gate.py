"""DB-03/SEC-FU-3: money receipts, vouchers, salary sheets and the finance
dashboard are Accounts-only.

Before this, any logged-in clerk (Office/Exam/HR) could open these pages
regardless of department, because the views only checked @login_required.
See docs/prompts/reports/DB-03.md, decision 1 (owner chose "restrict").

This pins: an Office-only or Exam-only clerk is refused (403) on all four
pages and the sidebar links are hidden for them; an Accounts clerk and the
superuser admin keep full access.
"""
from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Employee, Institution, InstitutionAccess, MoneyReceipt, SalarySheet, Voucher
from .permissions import sync_user_department_permissions

FINANCE_URLS = ('money_receipt_list', 'voucher_list', 'salary_sheet_list', 'finance_dashboard')


class FinanceDepartmentGateTests(TestCase):
    def setUp(self):
        self.institution = Institution.objects.create(name='Gate School', classes='6,7')

        self.office_clerk = get_user_model().objects.create_user(username='gate-office', password='password')
        InstitutionAccess.objects.create(user=self.office_clerk, institution=self.institution, department='Office')
        sync_user_department_permissions(self.office_clerk)

        self.exam_clerk = get_user_model().objects.create_user(username='gate-exam', password='password')
        InstitutionAccess.objects.create(user=self.exam_clerk, institution=self.institution, department='Exam')
        sync_user_department_permissions(self.exam_clerk)

        self.accounts_clerk = get_user_model().objects.create_user(username='gate-accounts', password='password')
        InstitutionAccess.objects.create(user=self.accounts_clerk, institution=self.institution, department='Accounts')
        sync_user_department_permissions(self.accounts_clerk)

        self.admin = get_user_model().objects.create_superuser(
            username='gate-admin', password='password', email='gate-admin@example.com',
        )

        employee = Employee.objects.create(
            institution=self.institution, name='Gate Employee', designation='Teacher',
            join_date=date(2026, 1, 1),
        )
        from .models import Student
        student = Student.objects.create(
            institution=self.institution, student_id='GATE001', name='Gate Student',
            admission_class='6', section='A', admission_year=2026,
        )
        MoneyReceipt.objects.create(
            student=student, receipt_no='RC-GATE-1', purpose='Fee',
            amount=100, date=date(2026, 1, 1),
        )
        Voucher.objects.create(
            institution=self.institution, purpose='Gate Voucher', amount=100,
            date=date(2026, 1, 1), status='UNPAID',
        )
        SalarySheet.objects.create(
            employee=employee, month='January 2026', amount=100,
            date=date(2026, 1, 1), status='UNPAID',
        )

    def _login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session['selected_institution_id'] = str(self.institution.pk)
        session.save()

    def test_office_clerk_is_refused_on_all_four_pages(self):
        self._login(self.office_clerk)
        for name in FINANCE_URLS:
            with self.subTest(view=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 403)

    def test_exam_clerk_is_refused_on_all_four_pages(self):
        self._login(self.exam_clerk)
        for name in FINANCE_URLS:
            with self.subTest(view=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 403)

    def test_accounts_clerk_keeps_access_to_all_four_pages(self):
        self._login(self.accounts_clerk)
        for name in FINANCE_URLS:
            with self.subTest(view=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)

    def test_admin_keeps_access_to_all_four_pages(self):
        self._login(self.admin)
        for name in FINANCE_URLS:
            with self.subTest(view=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)

    def test_sidebar_hides_accounts_group_for_office_clerk(self):
        self._login(self.office_clerk)
        response = self.client.get(reverse('dashboard'))
        self.assertNotContains(response, 'Money Receipts')
        self.assertNotContains(response, 'Finance Dashboard')

    def test_sidebar_shows_accounts_group_for_accounts_clerk(self):
        self._login(self.accounts_clerk)
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, 'Money Receipts')
        self.assertContains(response, 'Finance Dashboard')
