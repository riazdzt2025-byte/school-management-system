"""OF-06 — public success slip + public "check admission status" page.

These are the only applicant-facing pages that render somebody's personal data
without a login, so the privacy rules are pinned here next to the happy path:

* both pages carry ``noindex, nofollow`` and link to no internal route;
* every failed status check — unknown application number, wrong contact tail,
  malformed input — renders the *same* generic answer, so the page is not an
  application-number enumeration oracle;
* only the applicant's own masked name is shown; internal remarks, the acting
  user and money never appear;
* the P1-9 rate-limit counters slow repeated guessing per (address, application)
  pair and cap the total number of lookups from one address;
* no email/SMS notification is triggered by any of it (owner has not approved
  any notification channel).
"""
import re
from unittest import mock

from django.core.cache import caches
from django.template.loader import get_template
from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from django.urls import reverse

from .forms import normalize_application_number
from .models import AdmissionApplication, Institution, Student
from .views import (
    _PUBLIC_STATUS_CURRENT_STEP,
    PUBLIC_STATUS_FAIL_LIMIT,
    PUBLIC_STATUS_IP_LIMIT,
    PUBLIC_STATUS_MESSAGES,
    PUBLIC_STATUS_NOT_FOUND_ERROR,
    PUBLIC_STATUS_THROTTLE_ERROR,
    _mask_contact_tail,
    _mask_person_name,
    _public_status_timeline,
)

STATUS_URL = 'public_admission_status'
SLIP_URL = 'public_admission_success'

PUBLIC_TEMPLATES = (
    'students/public_admission_form.html',
    'students/public_admission_success.html',
    'students/public_admission_status.html',
)

# The only route names a public page may build a link to:
#   public_admission_apply     - the form itself
#   public_admission_status    - the status check (OF-06)
#   admission_dropdown_options - the form's own public JSON endpoint
PUBLIC_ROUTE_ALLOWLIST = {
    'public_admission_apply', 'public_admission_status', 'admission_dropdown_options',
}

INTERNAL_MARKERS = (
    'dashboard', 'admin', 'login', 'logout', 'admission_application_list',
    'admission_application_detail', 'class_section_summary', 'admission_funnel',
    'audit_log', 'student_list',
)


def template_source(name):
    with open(get_template(name).origin.name, encoding='utf-8') as handle:
        return handle.read()


def url_names(source):
    return set(re.findall(r"{%\s*url\s+'([^']+)'", source))


def internal_targets(html):
    """href/src values that point back at this site (not CDN, wa.me or anchors)."""
    targets = re.findall(r'(?:href|src)="([^"]+)"', html)
    return [
        target for target in targets
        if not target.startswith(('http://', 'https://', 'mailto:', '#', 'data:'))
    ]


def function_source(source, name):
    """The body of ``def name(...)`` up to the next top-level definition."""
    match = re.search(rf'\ndef {re.escape(name)}\(.*?(?=\ndef |\Z)', source, re.S)
    assert match, f'view {name} not found in the source'
    return match.group(0)


def strip_csrf(html):
    return re.sub(r'name="csrfmiddlewaretoken" value="[^"]+"', '', html)


def strip_echoed_number(html):
    """Blank the application number the visitor typed back into the form.

    It is the visitor's own input, so it is the only part of two failed answers
    that is allowed to differ — everything else must be byte-identical.
    """
    return re.sub(r'name="application_number" value="[^"]*"',
                  'name="application_number" value=""', html)


def comparable_body(response):
    return strip_echoed_number(strip_csrf(response.content.decode()))


class PublicSlipTests(TestCase):
    """The printable slip rendered right after a successful public POST."""

    def setUp(self):
        caches['ratelimit'].clear()
        self.institution = Institution.objects.create(name='Slip School', classes='6,9')
        self.data = {
            'institution': self.institution.pk,
            'applicant_name': 'Rahim Uddin',
            'date_of_birth': '2014-01-01',
            'gender': 'M',
            'religion': 'Islam',
            'applicant_address': 'Village',
            'guardian_name': 'Abdul Karim',
            'guardian_relation': 'Father',
            'guardian_contact_no': '01812345678',
            'guardian_address': 'Village',
            'requested_class': '6',
            'requested_section': 'A',
            'session': '2026-2027',
        }

    def _submit(self, **overrides):
        payload = dict(self.data, **overrides)
        return self.client.post(reverse('public_admission_apply'), payload)

    def test_slip_shows_the_application_details(self):
        response = self._submit()
        self.assertEqual(response.status_code, 200)
        application = AdmissionApplication.objects.get()
        for expected in (
            application.application_number,
            'Rahim Uddin',                       # the applicant's own name
            '6 / A',                             # requested class / section
            '2026-2027',                         # session
            'Slip School',                       # institution
            'What happens next',
            'Office review',
            'Admission payment',
            'Enrolment',
            _mask_contact_tail('01812345678'),
        ):
            with self.subTest(expected=expected):
                self.assertContains(response, expected)

    def test_slip_shows_when_it_was_submitted(self):
        response = self._submit()
        application = AdmissionApplication.objects.get()
        stamp = timezone.localtime(application.submitted_at).strftime('%d %b %Y')
        self.assertContains(response, stamp)

    def test_slip_hides_the_full_guardian_number(self):
        response = self._submit()
        self.assertNotContains(response, '01812345678')
        self.assertContains(response, '*******5678')

    def test_slip_is_printable(self):
        response = self._submit()
        html = response.content.decode()
        self.assertIn('@media print', html)
        self.assertIn('window.print()', html)
        self.assertIn('no-print', html)
        # The application number is on the slip itself, not just in a button.
        self.assertIn('id="application-number"', html)

    def test_slip_offers_copy_and_whatsapp_share(self):
        response = self._submit()
        html = response.content.decode()
        self.assertIn('navigator.clipboard', html)
        self.assertIn('id="copy-slip"', html)
        self.assertIn('https://wa.me/?text=', html)
        # The share text carries the applicant's own number and the public
        # status page only.
        self.assertIsNotNone(re.search(
            r'wa\.me/\?text=[^"]*APP-[0-9A-F]{12}[^"]*http%3A//testserver/admission/status/',
            html,
        ))
        self.assertIsNotNone(re.search(r'data-copy="[^"]*APP-[0-9A-F]{12}', html))

    def test_slip_links_only_to_public_pages(self):
        response = self._submit()
        html = response.content.decode()
        allowed = {reverse('public_admission_apply'), reverse('public_admission_status')}
        self.assertEqual(
            [target for target in internal_targets(html) if target not in allowed], [],
        )
        for marker in INTERNAL_MARKERS:
            with self.subTest(marker=marker):
                self.assertNotIn(marker, html)

    def test_slip_is_noindex(self):
        response = self._submit()
        self.assertContains(response, 'name="robots" content="noindex, nofollow"')

    def test_public_submission_sends_no_email_or_sms(self):
        with mock.patch('django.core.mail.send_mail') as send_mail, \
                mock.patch('django.core.mail.EmailMultiAlternatives') as email:
            response = self._submit()
        self.assertEqual(response.status_code, 200)
        send_mail.assert_not_called()
        email.assert_not_called()


class PublicStatusPageTests(TestCase):
    """The public "check your admission status" page."""

    def setUp(self):
        caches['ratelimit'].clear()
        self.institution = Institution.objects.create(name='Status School', classes='6,9')
        self.application = self._application(
            number='APP-11111111AAAA', status='SUBMITTED',
            applicant_name='Rahim Uddin', contact='01812345678',
        )

    def _application(self, number, status='SUBMITTED', applicant_name='Applicant One',
                     contact='01812345678', **extra):
        return AdmissionApplication.objects.create(
            application_number=number, institution=self.institution,
            applicant_name=applicant_name, guardian_name='Abdul Karim',
            guardian_contact_no=contact, requested_class='6',
            requested_section='A', session='2026-2027', status=status, **extra,
        )

    def _check(self, number, last4, **client_kwargs):
        return self.client.post(
            reverse(STATUS_URL),
            {'application_number': number, 'contact_last4': last4},
            **client_kwargs,
        )

    def _enrolled_application(self):
        student = Student.objects.create(
            institution=self.institution, name='Rahim Uddin',
            admission_class='6', section='A', guardian_contact_no='01812345678',
        )
        application = self._application(
            number='APP-22222222BBBB', status='ENROLLED',
            applicant_name='Rahim Uddin', enrolled_student=student,
        )
        return application, student

    def test_page_is_public_and_asks_for_two_factors(self):
        response = self.client.get(reverse(STATUS_URL))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="robots" content="noindex, nofollow"')
        self.assertContains(response, 'id_application_number')
        self.assertContains(response, 'id_contact_last4')

    def test_query_parameters_do_not_reveal_a_status(self):
        response = self.client.get(
            reverse(STATUS_URL),
            {'application_number': 'APP-11111111AAAA', 'contact_last4': '5678'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, PUBLIC_STATUS_MESSAGES['SUBMITTED'][0])
        self.assertNotContains(response, 'R***')

    def test_correct_details_show_the_status_with_a_masked_identity(self):
        response = self._check('APP-11111111AAAA', '5678')
        self.assertEqual(response.status_code, 200)
        for expected in (PUBLIC_STATUS_MESSAGES['SUBMITTED'][0], 'R*** U***', '*******5678'):
            with self.subTest(expected=expected):
                self.assertContains(response, expected)
        self.assertNotContains(response, 'Rahim Uddin')
        self.assertNotContains(response, 'Abdul Karim')

    def test_lowercase_and_prefixless_numbers_are_accepted(self):
        for typed in ('app-11111111aaaa', '11111111AAAA', ' APP-11111111AAAA '):
            with self.subTest(typed=typed):
                response = self._check(typed, '5678')
                self.assertContains(response, PUBLIC_STATUS_MESSAGES['SUBMITTED'][0])

    def test_every_status_has_its_own_applicant_facing_message(self):
        for index, status in enumerate(PUBLIC_STATUS_MESSAGES):
            with self.subTest(status=status):
                caches['ratelimit'].clear()
                application = self._application(
                    number=f'APP-{index:012X}', status=status,
                )
                response = self._check(application.application_number, '5678')
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, PUBLIC_STATUS_MESSAGES[status][0])
                self.assertContains(response, 'What happens next')
                self.assertNotContains(response, status)  # never the internal code

    def test_enrolled_application_shows_the_student_id(self):
        application, student = self._enrolled_application()
        response = self._check(application.application_number, '5678')
        self.assertContains(response, PUBLIC_STATUS_MESSAGES['ENROLLED'][0])
        self.assertContains(response, student.student_id)

    def test_rejected_shows_a_polite_message_and_never_the_office_remarks(self):
        application = self._application(
            number='APP-33333333CCCC', status='REJECTED',
            applicant_name='Rahim Uddin',
            office_remarks='Guardian not reachable — internal note 42',
        )
        response = self._check(application.application_number, '5678')
        self.assertContains(response, PUBLIC_STATUS_MESSAGES['REJECTED'][0])
        self.assertContains(response, 'contact the school office')
        self.assertNotContains(response, 'Guardian not reachable')
        self.assertNotContains(response, 'internal note 42')
        self.assertNotContains(response, 'Rahim Uddin')
        self.assertNotContains(response, 'Abdul Karim')

    def test_wrong_tail_returns_the_generic_answer_without_applicant_data(self):
        response = self._check('APP-11111111AAAA', '0000')
        self.assertContains(response, PUBLIC_STATUS_NOT_FOUND_ERROR)
        self.assertNotContains(response, 'Rahim Uddin')
        self.assertNotContains(response, 'R***')
        self.assertNotContains(response, PUBLIC_STATUS_MESSAGES['SUBMITTED'][0])

    def test_unknown_number_and_wrong_tail_are_indistinguishable(self):
        wrong_tail = comparable_body(self._check('APP-11111111AAAA', '0000'))
        unknown = comparable_body(self._check('APP-99999999ZZZZ', '0000'))
        self.assertContains(self._check('APP-11111111AAAA', '0000'), 'No application was found')
        self.assertEqual(wrong_tail, unknown)
        self.assertEqual(len(wrong_tail), len(unknown))
        self.assertIn(PUBLIC_STATUS_NOT_FOUND_ERROR, wrong_tail)

    def test_malformed_input_gives_the_same_generic_answer(self):
        for last4 in ('', '12', '12345'):
            with self.subTest(last4=last4):
                response = self._check('APP-11111111AAAA', last4)
                self.assertContains(response, PUBLIC_STATUS_NOT_FOUND_ERROR)
        response = self._check('', '5678')
        self.assertContains(response, PUBLIC_STATUS_NOT_FOUND_ERROR)

    def test_cross_applicant_data_never_leaks(self):
        other = self._application(
            number='APP-44444444DDDD', applicant_name='Karim Ahmed',
            contact='01700000000',
        )
        response = self._check('APP-11111111AAAA', '5678')
        self.assertNotContains(response, other.application_number)
        self.assertNotContains(response, 'K*** A***')
        self.assertNotContains(response, 'Karim Ahmed')
        # ... and the reverse direction (a wrong tail on the other applicant).
        response = self._check(other.application_number, '1234')
        self.assertContains(response, PUBLIC_STATUS_NOT_FOUND_ERROR)
        self.assertNotContains(response, 'R*** U***')
        self.assertNotContains(response, 'Rahim Uddin')

    def test_page_links_only_to_public_pages(self):
        response = self._check('APP-11111111AAAA', '5678')
        html = response.content.decode()
        allowed = {reverse('public_admission_apply'), reverse('public_admission_status')}
        self.assertEqual(
            [target for target in internal_targets(html) if target not in allowed], [],
        )

    def test_page_is_printable(self):
        response = self._check('APP-11111111AAAA', '5678')
        html = response.content.decode()
        self.assertIn('@media print', html)
        self.assertIn('window.print()', html)

    def test_repeated_wrong_attempts_block_one_pair_only(self):
        for _ in range(PUBLIC_STATUS_FAIL_LIMIT):
            response = self._check('APP-11111111AAAA', '0000')
            self.assertContains(response, PUBLIC_STATUS_NOT_FOUND_ERROR)
        # The pair is now locked — even with the right tail.
        blocked = self._check('APP-11111111AAAA', '5678')
        self.assertContains(blocked, PUBLIC_STATUS_THROTTLE_ERROR)
        self.assertNotContains(blocked, PUBLIC_STATUS_MESSAGES['SUBMITTED'][0])
        # Another application from the same address still works.
        other = self._application(number='APP-55555555EEEE', applicant_name='Karim Ahmed')
        response = self._check(other.application_number, '5678')
        self.assertContains(response, PUBLIC_STATUS_MESSAGES['SUBMITTED'][0])
        # ... and the lock is per address as well.
        response = self._check('APP-11111111AAAA', '5678', REMOTE_ADDR='203.0.113.7')
        self.assertContains(response, PUBLIC_STATUS_MESSAGES['SUBMITTED'][0])

    def test_walking_many_application_numbers_hits_the_address_budget(self):
        for index in range(PUBLIC_STATUS_IP_LIMIT):
            response = self._check(f'APP-{index:012X}', '1234')
            self.assertContains(response, PUBLIC_STATUS_NOT_FOUND_ERROR)
        over_budget = self._check('APP-99999999ZZZZ', '1234')
        self.assertContains(over_budget, PUBLIC_STATUS_THROTTLE_ERROR)
        # A different address is unaffected.
        response = self._check('APP-11111111AAAA', '5678', REMOTE_ADDR='203.0.113.42')
        self.assertContains(response, PUBLIC_STATUS_MESSAGES['SUBMITTED'][0])

    def test_throttle_cannot_be_bypassed_by_spoofing_xff(self):
        edge_ip = '198.51.100.20'
        for index in range(PUBLIC_STATUS_FAIL_LIMIT + 1):
            response = self._check(
                'APP-11111111AAAA', '0000',
                HTTP_X_FORWARDED_FOR=f'192.0.2.{index}, {edge_ip}',
            )
        self.assertContains(response, PUBLIC_STATUS_THROTTLE_ERROR)

    def test_status_check_sends_no_email_or_sms(self):
        with mock.patch('django.core.mail.send_mail') as send_mail, \
                mock.patch('django.core.mail.EmailMultiAlternatives') as email:
            self._check('APP-11111111AAAA', '5678')
            self._check('APP-11111111AAAA', '0000')
        send_mail.assert_not_called()
        email.assert_not_called()

    def test_public_views_contain_no_notification_calls(self):
        with open('students/views.py', encoding='utf-8') as handle:
            source = handle.read()
        for name in ('public_admission_apply', 'public_admission_status',
                     '_public_success_context', '_match_public_application'):
            body = function_source(source, name)
            with self.subTest(view=name):
                self.assertIsNone(
                    re.search(r'send_mail|EmailMessage|EmailMultiAlternatives|\bsms\b',
                              body, re.I),
                )


class PublicTemplatePinTests(SimpleTestCase):
    """Source-level pins that hold even for templates only rendered after a POST."""

    def test_public_templates_link_to_public_routes_only(self):
        for name in PUBLIC_TEMPLATES:
            source = template_source(name)
            with self.subTest(template=name):
                self.assertTrue(url_names(source) <= PUBLIC_ROUTE_ALLOWLIST, url_names(source))
                for marker in INTERNAL_MARKERS:
                    self.assertNotIn(marker, source)
                self.assertIn('name="robots" content="noindex, nofollow"', source)

    def test_status_and_success_templates_do_not_print_remarks_or_actors(self):
        for name in ('students/public_admission_success.html',
                     'students/public_admission_status.html'):
            source = template_source(name)
            with self.subTest(template=name):
                for forbidden in ('office_remarks', 'account_remarks', 'office_actor',
                                  'account_actor', 'payment_amount', 'next_step'):
                    self.assertNotIn(forbidden, source)


class PublicStatusWordingPinTests(SimpleTestCase):
    """Every stored status must have applicant-facing wording (no KeyError)."""

    def test_every_status_choice_has_a_public_message(self):
        codes = {code for code, _ in AdmissionApplication.STATUS_CHOICES}
        self.assertEqual(codes, set(PUBLIC_STATUS_MESSAGES))

    def test_every_open_status_has_a_timeline_stage(self):
        codes = {code for code, _ in AdmissionApplication.STATUS_CHOICES} - {'REJECTED'}
        self.assertEqual(codes, set(_PUBLIC_STATUS_CURRENT_STEP))


class PublicPageHelperTests(SimpleTestCase):
    """The masking / normalising helpers the public pages rely on."""

    def test_mask_person_name_keeps_the_first_letter_only(self):
        self.assertEqual(_mask_person_name('Rahim Uddin'), 'R*** U***')
        self.assertEqual(_mask_person_name('  rahim   uddin  '), 'R*** U***')
        self.assertEqual(_mask_person_name(''), '')
        self.assertEqual(_mask_person_name(None), '')
        # Fixed width, so the rendered page does not change size with the name.
        self.assertEqual(len(_mask_person_name('A')), len(_mask_person_name('Abcdefg')))

    def test_mask_contact_tail_hides_everything_but_four_digits(self):
        self.assertEqual(_mask_contact_tail('01812345678'), '*******5678')
        self.assertEqual(_mask_contact_tail('1234'), '1234')
        self.assertEqual(_mask_contact_tail(''), '')
        self.assertEqual(_mask_contact_tail(None), '')

    def test_normalize_application_number_tolerates_typing(self):
        self.assertEqual(normalize_application_number('APP-1a2b3c4d5e6f'), 'APP-1A2B3C4D5E6F')
        self.assertEqual(normalize_application_number(' app 1a2b3c4d5e6f '), 'APP-1A2B3C4D5E6F')
        self.assertEqual(normalize_application_number('1A2B3C4D5E6F'), 'APP-1A2B3C4D5E6F')
        self.assertEqual(normalize_application_number(''), '')
        self.assertEqual(normalize_application_number(None), '')
        self.assertEqual(normalize_application_number('nonsense'), 'NONSENSE')

    def test_timeline_marks_the_current_stage_only(self):
        application = AdmissionApplication(
            status='OFFICE_APPROVED', applicant_name='A', guardian_contact_no='01812345678',
            requested_class='6', session='2026-2027',
        )
        timeline = _public_status_timeline(application)
        self.assertEqual([step['state'] for step in timeline],
                         ['done', 'done', 'current', 'todo'])
        self.assertEqual([step['label'] for step in timeline[:2]],
                         ['Application received', 'Office review'])

    def test_rejected_timeline_is_closed(self):
        application = AdmissionApplication(
            status='REJECTED', applicant_name='A', guardian_contact_no='01812345678',
            requested_class='6', session='2026-2027',
        )
        timeline = _public_status_timeline(application)
        self.assertEqual([step['state'] for step in timeline], ['done', 'closed'])
