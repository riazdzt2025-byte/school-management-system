"""Tests for P1-3: auto-generated receipt numbers for manual money receipts.

`receipt_no` is no longer user-editable: it is generated on create (RC-<year>-<code>)
and never changes on edit. Two receipts created back-to-back must get distinct,
well-formed numbers, and the `MoneyReceiptForm` must not expose the field.
"""
import re
from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .forms import MoneyReceiptForm
from .models import Institution, MoneyReceipt, Student

RC_PATTERN = re.compile(r"RC-\d{4}-[0-9A-F]{10}")


class AutoReceiptNumberTests(TestCase):
    def setUp(self):
        self.institution = Institution.objects.create(name='School', classes='6,7,9')
        self.user = get_user_model().objects.create_user(
            username='acc', password='password',
        )
        from django.contrib.auth.models import Permission
        add_perm = Permission.objects.get(codename='add_moneyreceipt')
        change_perm = Permission.objects.get(codename='change_moneyreceipt')
        self.user.user_permissions.add(add_perm, change_perm)
        self.student = Student.objects.create(
            institution=self.institution, student_id='S001', name='Student One',
            admission_class='6', section='A', admission_year=2026, roll_no=1,
            gender='M', religion='Islam',
        )

    def test_form_does_not_expose_receipt_no_field(self):
        form = MoneyReceiptForm(data={'student': self.student.pk,
                                      'purpose': 'Fee',
                                      'amount': '100.00', 'date': '2026-01-01'},
                                user=self.user)
        self.assertNotIn('receipt_no', form.fields)
        self.assertTrue(form.is_valid())

    def test_create_two_receipts_gets_distinct_auto_numbers(self):
        url = reverse('add_money_receipt')
        payload = {'student': self.student.pk, 'purpose': 'Fee',
                   'amount': '100.00', 'date': '2026-01-01'}
        self.client.force_login(self.user)

        r1 = self.client.post(url, {**payload, 'receipt_no': 'HACK-1'})
        self.assertEqual(r1.status_code, 302)  # redirect = success
        r2 = self.client.post(url, payload)
        self.assertEqual(r2.status_code, 302)

        receipts = MoneyReceipt.objects.order_by('id')
        self.assertEqual(receipts.count(), 2)
        n1, n2 = receipts[0].receipt_no, receipts[1].receipt_no
        self.assertTrue(RC_PATTERN.match(n1), n1)
        self.assertTrue(RC_PATTERN.match(n2), n2)
        # The hand-crafted number must NOT have been used.
        self.assertNotIn('HACK-1', (n1, n2))
        self.assertNotEqual(n1, n2)

    def test_edit_preserves_receipt_no(self):
        receipt = MoneyReceipt.objects.create(
            student=self.student, receipt_no='RC-2026-ABCDEF1234',
            purpose='Fee', amount=100, date=date(2026, 1, 1), created_by=self.user,
        )
        self.client.force_login(self.user)
        url = reverse('edit_money_receipt', args=[receipt.pk])
        response = self.client.post(url, {
            'student': self.student.pk, 'purpose': 'Updated',
            'amount': '150.00', 'date': '2026-01-02',
        })
        self.assertEqual(response.status_code, 302)
        receipt.refresh_from_db()
        self.assertEqual(receipt.receipt_no, 'RC-2026-ABCDEF1234')
        self.assertEqual(receipt.purpose, 'Updated')
