"""Regression tests for server-side money validation (P0-5 / SEC-7).

A hand-crafted POST must not store a negative or over-sized amount on any of
the four money fields — the HTML ``min=``/``max=`` attributes are client-side
only. Each form now applies ``MinValueValidator(0)`` and
``MaxValueValidator(99999999.99)`` (max_digits=10, decimal_places=2) on the
server.
"""
from datetime import date

from django.test import TestCase
from django.contrib.auth import get_user_model

from .forms import (
    AdmissionPaymentForm, MoneyReceiptForm, SalarySheetForm, VoucherForm,
)
from .models import AdmissionApplication, Employee, Institution, Student


class MoneyValidatorTests(TestCase):
    def setUp(self):
        self.institution = Institution.objects.create(name='School', classes='6,7,9')
        self.user = get_user_model().objects.create_user(
            username='acc', password='password',
        )
        self.student = Student.objects.create(
            institution=self.institution, student_id='S001', name='Student One',
            admission_class='6', section='A', admission_year=2026, roll_no=1,
            gender='M', religion='Islam',
        )
        self.employee = Employee.objects.create(
            institution=self.institution, name='Emp One', designation='Teacher',
            join_date=date(2026, 1, 1),
        )
        self.application = AdmissionApplication.objects.create(
            institution=self.institution, applicant_name='App One',
            guardian_name='Guard One',
            guardian_contact_no='01900000000', requested_class='6',
            session='2026-2027', status='ACCOUNT_PENDING',
        )

    def _assert_rejects(self, form):
        self.assertFalse(form.is_valid())
        self.assertTrue(form.errors)

    def test_admission_payment_amount_rejects_negative(self):
        form = AdmissionPaymentForm(data={'payment_amount': '-50.00',
                                          'payment_date': '2026-01-01'})
        self._assert_rejects(form)

    def test_admission_payment_amount_rejects_oversize(self):
        form = AdmissionPaymentForm(data={'payment_amount': '999999999.99',
                                          'payment_date': '2026-01-01'})
        self._assert_rejects(form)

    def test_admission_payment_amount_accepts_zero_and_positive(self):
        # payment_purpose is required, so include it alongside the amount.
        form = AdmissionPaymentForm(data={'payment_amount': '0.00',
                                          'payment_date': '2026-01-01',
                                          'payment_purpose': 'Admission Fee'})
        self.assertTrue(form.is_valid())
        form = AdmissionPaymentForm(data={'payment_amount': '1500.50',
                                          'payment_date': '2026-01-01',
                                          'payment_purpose': 'Admission Fee'})
        self.assertTrue(form.is_valid())

    def test_money_receipt_amount_rejects_negative(self):
        form = MoneyReceiptForm(data={'student': self.student.pk,
                                      'receipt_no': 'R-1', 'purpose': 'Fee',
                                      'amount': '-1.00', 'date': '2026-01-01'},
                                user=self.user)
        self._assert_rejects(form)

    def test_money_receipt_amount_rejects_oversize(self):
        form = MoneyReceiptForm(data={'student': self.student.pk,
                                      'receipt_no': 'R-2', 'purpose': 'Fee',
                                      'amount': '999999999.99', 'date': '2026-01-01'},
                                user=self.user)
        self._assert_rejects(form)

    def test_voucher_amount_rejects_negative(self):
        form = VoucherForm(data={'purpose': 'Rent', 'amount': '-5.00',
                                 'date': '2026-01-01', 'status': 'UNPAID'})
        self._assert_rejects(form)

    def test_salary_sheet_amount_rejects_negative(self):
        form = SalarySheetForm(data={'employee': self.employee.pk,
                                     'month': 'January 2026', 'amount': '-100.00',
                                     'date': '2026-01-01', 'status': 'UNPAID'},
                               user=self.user)
        self._assert_rejects(form)

    def test_voucher_and_salary_accept_valid_positive_amount(self):
        voucher = VoucherForm(data={'purpose': 'Rent', 'amount': '5000.00',
                                    'date': '2026-01-01', 'status': 'UNPAID'})
        self.assertTrue(voucher.is_valid())
        salary = SalarySheetForm(data={'employee': self.employee.pk,
                                       'month': 'February 2026', 'amount': '15000.00',
                                       'date': '2026-01-01', 'status': 'UNPAID'},
                                 user=self.user)
        self.assertTrue(salary.is_valid())
