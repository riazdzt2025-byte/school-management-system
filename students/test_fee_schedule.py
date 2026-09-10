"""Tests for P1-2: class-wise fee schedule (pre-fill + mismatch warning)."""
from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from .models import AdmissionApplication, Fee, Institution, InstitutionAccess, Student


class FeeScheduleTests(TestCase):
    def setUp(self):
        self.institution = Institution.objects.create(name='School', classes='6')
        self.accounts = get_user_model().objects.create_user(
            username='acc', password='password',
        )
        self.accounts.user_permissions.add(
            Permission.objects.get(codename='change_admissionapplication'),
            Permission.objects.get(codename='view_admissionapplication'),
        )
        InstitutionAccess.objects.create(
            user=self.accounts, institution=self.institution, department='Accounts',
        )
        self.application = AdmissionApplication.objects.create(
            institution=self.institution, applicant_name='App One',
            guardian_name='Guard One',
            guardian_contact_no='01900000000', requested_class='6',
            session='2026-2027', status='ACCOUNT_PENDING',
        )
        self.account_login()

    def account_login(self):
        self.client.force_login(self.accounts)
        session = self.client.session
        session['selected_institution_id'] = str(self.institution.pk)
        session['selected_department'] = 'Accounts'
        session.save()

    def test_fee_prefills_amount_on_detail(self):
        Fee.objects.create(
            institution=self.institution, admission_class='6',
            purpose='Admission Fee', amount=1500,
        )
        response = self.client.get(reverse('admission_application_detail',
                                            args=[self.application.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['fee'].amount, 1500)
        self.assertEqual(response.context['payment_form'].initial['payment_amount'], 1500)
        self.assertIn('value="1500.00"', response.content.decode())
        self.assertIn('Fee schedule for Class 6', response.content.decode())

    def test_fee_mismatch_warns_but_approves(self):
        Fee.objects.create(
            institution=self.institution, admission_class='6',
            purpose='Admission Fee', amount=1500,
        )
        response = self.client.post(
            reverse('accounts_approve_payment', args=[self.application.pk]),
            {'payment_amount': '2000.00', 'payment_date': '2026-01-01',
             'payment_purpose': 'Admission Fee'},
        )
        self.assertEqual(response.status_code, 302)
        messages = list(response.wsgi_request._messages) if hasattr(response.wsgi_request, '_messages') else []
        from django.contrib.messages import get_messages
        msgs = [m.message for m in get_messages(response.wsgi_request)]
        self.assertTrue(any('differs from the fee schedule' in m for m in msgs))
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, 'ENROLLED')

    def test_no_fee_still_approves_without_warning(self):
        response = self.client.post(
            reverse('accounts_approve_payment', args=[self.application.pk]),
            {'payment_amount': '2000.00', 'payment_date': '2026-01-01',
             'payment_purpose': 'Admission Fee'},
        )
        self.assertEqual(response.status_code, 302)
        from django.contrib.messages import get_messages
        msgs = [m.message for m in get_messages(response.wsgi_request)]
        self.assertTrue(all('differs from the fee schedule' not in m for m in msgs))
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, 'ENROLLED')
        self.assertTrue(Student.objects.filter(
            admission_application=self.application).exists())
