"""O4 — the admission funnel report (Office → Reports).

The funnel counts applications per status (SUBMITTED → OFFICE_APPROVED →
ACCOUNT_PENDING → PAYMENT_APPROVED → ENROLLED, with REJECTED listed beside it),
optionally bounded by a ``submitted_at`` date range. These tests lock the three
things that matter here: the counts themselves, that they are institution-scoped
(a clerk may neither read nor export another school's numbers), and that the
Excel export works without disturbing ``download_admission_sheet``.

Query-only feature — no models, no migrations, and the SSC Registration / Board
Result surfaces stay retired.
"""
import re
import unittest
from datetime import datetime, time, timedelta
from io import BytesIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.template.loader import get_template
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

try:
    from openpyxl import load_workbook
except ModuleNotFoundError:  # pragma: no cover - openpyxl is a hard dependency
    load_workbook = None

from .models import AdmissionApplication, Institution, InstitutionAccess

requires_openpyxl = unittest.skipIf(load_workbook is None, 'openpyxl is required for the Excel export tests')

FUNNEL_PAGE = 'admission_funnel_report'
FUNNEL_EXPORT = 'admission_funnel_export'

# status -> how many applications this fixture puts in it, per institution.
FIXTURE_COUNTS = {
    'SUBMITTED': 3,
    'OFFICE_APPROVED': 2,
    'ACCOUNT_PENDING': 1,
    'PAYMENT_APPROVED': 1,
    'ENROLLED': 2,
    'REJECTED': 1,
}
TOTAL_A = sum(FIXTURE_COUNTS.values())          # 10
TOTAL_B = TOTAL_A + 4                           # B gets 4 extra SUBMITTED rows

LABELS = dict(AdmissionApplication.STATUS_CHOICES)


def _count_on_page(response, status):
    """The number the stage table shows for one status."""
    body = response.content.decode()
    match = re.search(
        rf'<td>{re.escape(LABELS[status])}</td>\s*<td class="num">(\d+)</td>', body,
    )
    if match is None:
        raise AssertionError(f'{LABELS[status]} row not found in the funnel table')
    return int(match.group(1))


def _funnel_sheet(workbook):
    """{label: count} for the stage rows of the exported sheet."""
    rows = list(workbook['Admission Funnel'].iter_rows(values_only=True))
    header = rows.index(('Status', 'Applications', '% of total'))
    counts = {}
    for row in rows[header + 1:]:
        if row[0] is None or row[0] == '':
            break
        counts[row[0]] = row[1]
    return counts


class AdmissionFunnelReportTests(TestCase):
    """Funnel counts, institution isolation, permission guards and the export."""

    def setUp(self):
        self.institution_a = Institution.objects.create(name='Funnel A', classes='6,7')
        self.institution_b = Institution.objects.create(name='Funnel B', classes='6,7')

        self.admin = get_user_model().objects.create_superuser(
            username='funnel-admin', password='password', email='funnel@example.com',
        )
        # Office clerk scoped to A only, and the same for the Accounts
        # department (both are meant to be able to read the report).
        self.office_clerk = self._clerk('funnel-office', 'Office')
        self.accounts_clerk = self._clerk('funnel-accounts', 'Accounts')
        # An Exam clerk holds no admission view permission at all.
        self.exam_clerk = get_user_model().objects.create_user(
            username='funnel-exam', password='password',
        )
        InstitutionAccess.objects.create(
            user=self.exam_clerk, institution=self.institution_a, department='Exam',
        )

        for status, count in FIXTURE_COUNTS.items():
            for index in range(count):
                self._application(self.institution_a, status, name=f'A {status} {index}')
        for status, count in FIXTURE_COUNTS.items():
            extra = 4 if status == 'SUBMITTED' else 0
            for index in range(count + extra):
                self._application(self.institution_b, status, name=f'B {status} {index}')

    # ------------------------------------------------------------------ helpers
    def _clerk(self, username, department):
        user = get_user_model().objects.create_user(username=username, password='password')
        InstitutionAccess.objects.create(
            user=user, institution=self.institution_a, department=department,
        )
        user.user_permissions.add(
            Permission.objects.get(
                content_type=ContentType.objects.get_for_model(AdmissionApplication),
                codename='view_admissionapplication',
            )
        )
        return user

    def _application(self, institution, status, name=None, submitted_at=None):
        application = AdmissionApplication.objects.create(
            institution=institution,
            applicant_name=name or f'{status} applicant',
            guardian_name='Guardian', guardian_contact_no='01900000000',
            requested_class='6', session='2026-2027', status=status,
        )
        if submitted_at is not None:
            # ``submitted_at`` is auto_now_add, so a fixture that needs a
            # specific date sets it through the queryset (which skips it).
            AdmissionApplication.objects.filter(pk=application.pk).update(
                submitted_at=timezone.make_aware(submitted_at),
            )
        return application

    def _login(self, user, institution=None, department='Office'):
        self.client.force_login(user)
        session = self.client.session
        if institution is not None:
            session['selected_institution_id'] = str(institution.pk)
        session['selected_department'] = department
        session.save()

    # ------------------------------------------------------------- the counts
    def test_reports_show_funnel_counts(self):
        """Every stage carries its own count, in funnel order, for the whole scope."""
        self._login(self.admin)
        response = self.client.get(reverse(FUNNEL_PAGE))
        self.assertEqual(response.status_code, 200)

        # Both institutions hold FIXTURE_COUNTS applications, and B carries 4
        # extra SUBMITTED ones, so the all-institution total is exactly that.
        expected = {status: count * 2 for status, count in FIXTURE_COUNTS.items()}
        expected['SUBMITTED'] += 4
        self.assertEqual(sum(expected.values()), TOTAL_A + TOTAL_B)
        for status, count in expected.items():
            with self.subTest(status=status):
                self.assertEqual(_count_on_page(response, status), count)

        total = TOTAL_A + TOTAL_B
        self.assertContains(response, f'Total applications: {total}')
        self.assertEqual(response.context['total_applications'], total)
        self.assertEqual(response.context['enrolled'], expected['ENROLLED'])
        self.assertEqual(response.context['rejected'], expected['REJECTED'])
        self.assertEqual(
            response.context['in_progress'],
            total - expected['ENROLLED'] - expected['REJECTED'],
        )
        # Conversion is enrolled over total, and the page never divides by zero.
        self.assertEqual(
            response.context['conversion_percent'],
            round(expected['ENROLLED'] * 100 / total, 1),
        )
        # An all-institution scope also breaks the same numbers down per school.
        breakdown = {row['institution']: row['total'] for row in response.context['institution_rows']}
        self.assertEqual(breakdown, {'Funnel A': TOTAL_A, 'Funnel B': TOTAL_B})

    def test_report_page_is_print_ready(self):
        """A print header carries the title; the controls drop out of a printout."""
        self._login(self.admin)
        response = self.client.get(reverse(FUNNEL_PAGE))
        body = response.content.decode()
        self.assertIn('<div class="print-header">', body)
        self.assertIn('<p>Admission Funnel Report</p>', body)
        # Filters / Excel / print buttons are marked so @media print hides them,
        # while the scope + date line above stays on the paper.
        self.assertIn('class="page-actions d-flex gap-2 d-print-none"', body)
        self.assertIn('Total applications: {}'.format(TOTAL_A + TOTAL_B), body)
        # The Excel download is offered with the current filters attached.
        self.assertIn(reverse(FUNNEL_EXPORT), body)

    def test_reports_funnel_counts_respect_the_institution_filter(self):
        """?institution=<id> narrows the counts to that institution only."""
        self._login(self.admin)
        response = self.client.get(reverse(FUNNEL_PAGE), {'institution': self.institution_a.pk})
        self.assertEqual(response.status_code, 200)
        for status, count in FIXTURE_COUNTS.items():
            with self.subTest(status=status):
                self.assertEqual(_count_on_page(response, status), count)
        self.assertContains(response, f'Total applications: {TOTAL_A}')
        # A single-institution view has no per-institution breakdown to show,
        # and the Excel link keeps the same filter.
        self.assertEqual(len(response.context['institution_rows']), 0)
        self.assertEqual(response.context['institution'], self.institution_a)
        self.assertIn(f'institution={self.institution_a.pk}', response.context['export_url'])

    def test_reports_funnel_counts_honour_the_submitted_at_date_range(self):
        """from/to bound submitted_at inclusively — whole days, both ends."""
        # A window four weeks back, so the auto-created fixtures ('now') can
        # never fall inside it and the expected counts stay deterministic.
        base = timezone.localdate() - timedelta(days=40)
        self._application(
            self.institution_a, 'SUBMITTED', name='First day, noon',
            submitted_at=datetime.combine(base, time(12, 0)),
        )
        self._application(
            self.institution_a, 'ENROLLED', name='Last day, late',
            submitted_at=datetime.combine(base + timedelta(days=1), time(23, 59)),
        )
        self._application(
            self.institution_a, 'REJECTED', name='Day after, just past midnight',
            submitted_at=datetime.combine(base + timedelta(days=2), time(0, 1)),
        )
        self._login(self.admin)

        window = self.client.get(reverse(FUNNEL_PAGE), {
            'institution': self.institution_a.pk,
            'from': base.isoformat(),
            'to': (base + timedelta(days=1)).isoformat(),
        })
        self.assertEqual(window.status_code, 200)
        self.assertEqual(window.context['total_applications'], 2)
        self.assertEqual(_count_on_page(window, 'SUBMITTED'), 1)
        self.assertEqual(_count_on_page(window, 'ENROLLED'), 1)
        self.assertEqual(_count_on_page(window, 'REJECTED'), 0)

        # Empty window: the page says so instead of dividing by zero.
        empty = self.client.get(reverse(FUNNEL_PAGE), {
            'institution': self.institution_a.pk,
            'from': (base - timedelta(days=5)).isoformat(),
            'to': (base - timedelta(days=4)).isoformat(),
        })
        self.assertEqual(empty.context['total_applications'], 0)
        self.assertEqual(empty.context['conversion_percent'], 0.0)
        self.assertContains(empty, 'No applications match this filter.')

        # The filter carries over to the export URL the page links to.
        self.assertIn('from=', window.context['export_url'])
        self.assertIn('to=', window.context['export_url'])

        # An unparseable date is ignored rather than raising.
        broken = self.client.get(reverse(FUNNEL_PAGE), {'from': 'not-a-date'})
        self.assertEqual(broken.status_code, 200)
        self.assertEqual(broken.context['total_applications'], TOTAL_A + TOTAL_B + 3)

    # ------------------------------------------------- institution isolation
    @requires_openpyxl
    def test_reports_scoped_by_institution(self):
        """A clerk scoped to A counts A's applications and never B's."""
        self._login(self.office_clerk, institution=self.institution_a)
        response = self.client.get(reverse(FUNNEL_PAGE))
        self.assertEqual(response.status_code, 200)
        for status, count in FIXTURE_COUNTS.items():
            with self.subTest(status=status):
                self.assertEqual(_count_on_page(response, status), count)
        self.assertEqual(response.context['total_applications'], TOTAL_A)
        self.assertNotContains(response, 'Funnel B')

        # The same through the export: no second school's numbers leak.
        export = self.client.get(reverse(FUNNEL_EXPORT))
        self.assertEqual(export.status_code, 200)
        workbook = load_workbook(BytesIO(export.content), data_only=True)
        counts = _funnel_sheet(workbook)
        self.assertEqual(counts[LABELS['ENROLLED']], FIXTURE_COUNTS['ENROLLED'])
        self.assertEqual(counts[LABELS['SUBMITTED']], FIXTURE_COUNTS['SUBMITTED'])
        self.assertNotIn('By Institution', workbook.sheetnames)
        self.assertNotIn('Funnel B', ' '.join(str(cell) for row in
                                               workbook['Admission Funnel'].iter_rows(values_only=True)
                                               for cell in row))

    @requires_openpyxl
    def test_reports_institution_query_param_cannot_escape_scope(self):
        """?institution=<B> on the funnel page and export still shows A only."""
        self._login(self.office_clerk, institution=self.institution_a)
        for url in (reverse(FUNNEL_PAGE), reverse(FUNNEL_EXPORT)):
            with self.subTest(url=url):
                response = self.client.get(url, {'institution': self.institution_b.pk})
                self.assertEqual(response.status_code, 200)
                if url.endswith('export/'):
                    rows = list(load_workbook(
                        BytesIO(response.content), data_only=True,
                    )['Admission Funnel'].iter_rows(values_only=True))
                    text = ' '.join(str(cell) for row in rows for cell in row)
                    self.assertIn('Funnel A', text)
                    self.assertNotIn('Funnel B', text)
                else:
                    self.assertEqual(response.context['total_applications'], TOTAL_A)
                    self.assertNotContains(response, 'Funnel B')

    def test_reports_scoped_when_session_loses_its_institution(self):
        """A clerk whose session has no institution still counts only their own set."""
        self._login(self.office_clerk)
        session = self.client.session
        session['selected_institution_id'] = ''
        session.save()
        response = self.client.get(reverse(FUNNEL_PAGE))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total_applications'], TOTAL_A)
        self.assertNotContains(response, 'Funnel B')

    @requires_openpyxl
    def test_admin_export_adds_the_by_institution_breakdown(self):
        self._login(self.admin)
        response = self.client.get(reverse(FUNNEL_EXPORT))
        self.assertEqual(response.status_code, 200)
        workbook = load_workbook(BytesIO(response.content), data_only=True)
        self.assertIn('By Institution', workbook.sheetnames)
        rows = list(workbook['By Institution'].iter_rows(values_only=True))
        header = rows[0]
        by_name = {row[0]: dict(zip(header[1:], row[1:])) for row in rows[1:]}
        self.assertEqual(by_name['Funnel A'][LABELS['ENROLLED']], FIXTURE_COUNTS['ENROLLED'])
        self.assertEqual(by_name['Funnel B'][LABELS['SUBMITTED']], FIXTURE_COUNTS['SUBMITTED'] + 4)
        self.assertEqual(by_name['All Institutions'][LABELS['SUBMITTED']], FIXTURE_COUNTS['SUBMITTED'] * 2 + 4)

    # ------------------------------------------------------ permission guards
    def test_reports_url_guard_rejects_unauthorised_users(self):
        """The direct URLs are guarded; hiding the menu entry is not the security."""
        for url in (reverse(FUNNEL_PAGE), reverse(FUNNEL_EXPORT)):
            with self.subTest(url=url):
                # Anonymous: pushed to the login page, not a data leak.
                self.client.logout()
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertIn(reverse('login'), response.url)

                # Logged in, institution access, but no view permission at all:
                # the URL itself is guarded, so hiding the menu is not the only
                # thing standing between a clerk and another department's data.
                self._login(self.exam_clerk, institution=self.institution_a)
                self.assertEqual(self.client.get(url).status_code, 403)

    def test_reports_allow_the_accounts_department(self):
        """Accounts reads the same funnel (it owns the payment stages)."""
        self._login(self.accounts_clerk, institution=self.institution_a, department='Accounts')
        response = self.client.get(reverse(FUNNEL_PAGE))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total_applications'], TOTAL_A)

    def test_reports_department_guard_blocks_other_departments(self):
        """Holding the permission is not enough from a department that does not run admissions."""
        self.exam_clerk.user_permissions.add(
            Permission.objects.get(
                content_type=ContentType.objects.get_for_model(AdmissionApplication),
                codename='view_admissionapplication',
            )
        )
        self._login(self.exam_clerk, institution=self.institution_a, department='Exam')
        response = self.client.get(reverse(FUNNEL_PAGE))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('dashboard'), response.url)

    def test_reports_nav_link_shown_only_to_authorised_users(self):
        url = reverse(FUNNEL_PAGE)
        self._login(self.office_clerk, institution=self.institution_a)
        self.assertIn(f'href="{url}"', self.client.get(reverse('dashboard')).content.decode())

        bare = get_user_model().objects.create_user(username='funnel-bare', password='password')
        self._login(bare)
        self.assertNotIn(f'href="{url}"', self.client.get(reverse('dashboard')).content.decode())

    # ----------------------------------------------------------- the export
    @requires_openpyxl
    def test_report_excel_export(self):
        """A funnel workbook with the counts, the scope and the date range in it."""
        self._application(
            self.institution_a, 'SUBMITTED', name='Dated row',
            submitted_at=datetime(2026, 1, 5, 9, 0),
        )
        self._login(self.admin)
        response = self.client.get(reverse(FUNNEL_EXPORT), {
            'from': '2026-01-01', 'to': '2026-01-31', 'institution': self.institution_a.pk,
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        self.assertIn('admission_funnel_report.xlsx', response['Content-Disposition'])

        workbook = load_workbook(BytesIO(response.content), data_only=True)
        self.assertEqual(workbook.sheetnames, ['Admission Funnel'])
        counts = _funnel_sheet(workbook)
        # Only the January row, in the filtered institution — and the stage
        # order in the sheet is the funnel order, not an arbitrary GROUP BY.
        self.assertEqual(list(counts), [LABELS[key] for key in [
            'SUBMITTED', 'OFFICE_APPROVED', 'ACCOUNT_PENDING', 'PAYMENT_APPROVED', 'ENROLLED', 'REJECTED',
        ]])
        self.assertEqual(counts[LABELS['SUBMITTED']], 1)
        for status in ('OFFICE_APPROVED', 'ACCOUNT_PENDING', 'PAYMENT_APPROVED', 'ENROLLED', 'REJECTED'):
            self.assertEqual(counts[LABELS[status]], 0)

        rows = list(workbook['Admission Funnel'].iter_rows(values_only=True))
        meta = {row[0]: row[1] for row in rows if row[0] and row[0] != 'Status' and len(row) > 1}
        self.assertEqual(meta['Institution'], 'Funnel A')
        self.assertEqual(meta['Submitted from'], '2026-01-01')
        self.assertEqual(meta['Submitted to'], '2026-01-31')
        self.assertEqual(meta['Total applications'], 1)
        self.assertEqual(meta['Conversion (enrolled / total) %'], 0.0)

    @requires_openpyxl
    def test_report_excel_export_empty_scope_does_not_crash(self):
        """Zero applications is a sheet of zeroes, not a division-by-zero page."""
        AdmissionApplication.objects.all().delete()
        self._login(self.admin)
        response = self.client.get(reverse(FUNNEL_EXPORT))
        self.assertEqual(response.status_code, 200)
        counts = _funnel_sheet(load_workbook(BytesIO(response.content), data_only=True))
        self.assertEqual(set(counts.values()), {0})
        self.assertEqual(self.client.get(reverse(FUNNEL_PAGE)).status_code, 200)

    @requires_openpyxl
    def test_download_admission_sheet_still_exports_the_application_rows(self):
        """The per-application export is untouched by the new report."""
        self._login(self.admin)
        response = self.client.get(reverse('download_admission_sheet'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('admission_sheet.xlsx', response['Content-Disposition'])
        workbook = load_workbook(BytesIO(response.content), data_only=True)
        self.assertIn('Funnel A', workbook.sheetnames)
        applicants = [
            row[1] for row in workbook['Funnel A'].iter_rows(min_row=2, values_only=True)
        ]
        self.assertIn('A ENROLLED 0', applicants)
        self.assertIn('A SUBMITTED 0', applicants)

    def test_share_application_link_is_untouched(self):
        """O4 must not disturb the admission list page it sits beside."""
        self._login(self.office_clerk, institution=self.institution_a)
        response = self.client.get(reverse('admission_application_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Share Application Link')
        self.assertContains(response, reverse('public_admission_apply'))

    # --------------------- the Admission page Reports link (ADM-REPORTS follow-up)
    # The owner's original requirement was the report *beside Share Application
    # Link* on the internal Admission page, not only in the Office flyout. These
    # lock that placement, the URL it points at, the institution scope it carries
    # and the fact that nobody unauthorised ever gets the link.
    def test_admission_page_shows_reports_link_beside_the_share_link(self):
        """Reports sits next to Share Application Link and uses the named URL."""
        self._login(self.office_clerk, institution=self.institution_a)
        response = self.client.get(reverse('admission_application_list'))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        url = reverse(FUNNEL_PAGE)

        anchor = re.search(r'<a[^>]*id="admission-reports-link"[^>]*>', body)
        self.assertIsNotNone(anchor, 'Reports action missing from the Admission page')
        self.assertIn(f'href="{url}"', anchor.group(0))
        # The label is bilingual, matching how the owner asked for it.
        self.assertIn('Reports', body)
        self.assertIn('রিপোর্টস', body)

        # Placement: after the share action, which itself stays intact.
        self.assertIn('Share Application Link', body)
        self.assertGreater(
            body.index('admission-reports-link'), body.index('share-application-link-btn'),
            'Reports must sit beside (after) Share Application Link',
        )

        # Both entry points coexist — this follow-up adds the page action without
        # removing the existing Office flyout link rendered by base.html.
        self.assertGreaterEqual(body.count(f'href="{url}"'), 2)

    def test_admission_page_reports_link_keeps_the_session_institution(self):
        """Following the link lands on the same institution scope the list uses."""
        self._login(self.office_clerk, institution=self.institution_a)
        body = self.client.get(reverse('admission_application_list')).content.decode()
        anchor = re.search(r'<a[^>]*id="admission-reports-link"[^>]*>', body)
        href = re.search(r'href="([^"]+)"', anchor.group(0)).group(1)

        # No institution id travels in the URL: the report resolves the same
        # session selection the list page filters by, so there is nothing a
        # scoped clerk could tamper with to widen the scope.
        self.assertEqual(href, reverse(FUNNEL_PAGE))
        self.assertNotIn('institution=', href)

        report = self.client.get(href)
        self.assertEqual(report.status_code, 200)
        self.assertEqual(report.context['total_applications'], TOTAL_A)
        self.assertNotContains(report, 'Funnel B')

    def test_admission_page_reports_link_is_denied_to_unauthorised_users(self):
        """No permission → no page and no link; wrong department → redirected."""
        url = reverse(FUNNEL_PAGE)
        list_url = reverse('admission_application_list')

        # Anonymous: bounced to login, so no internal action is rendered at all.
        self.client.logout()
        anonymous = self.client.get(list_url)
        self.assertEqual(anonymous.status_code, 302)
        self.assertIn(reverse('login'), anonymous.url)
        self.assertNotIn(url, anonymous.content.decode())

        # Institution access but no view_admissionapplication permission: the
        # Admission page answers 403, so the Reports action cannot appear — and
        # typing the report URL directly is refused the same way.
        self._login(self.exam_clerk, institution=self.institution_a, department='Exam')
        forbidden = self.client.get(list_url)
        self.assertEqual(forbidden.status_code, 403)
        self.assertNotIn(url, forbidden.content.decode())
        self.assertEqual(self.client.get(url).status_code, 403)

        # Holding the permission is not enough from a department that does not run
        # admissions: both the page and the report redirect to the dashboard, so
        # the link is never a dead end for anybody who can actually see it.
        exam_with_perm = self._clerk('funnel-exam-perm', 'Exam')
        self._login(exam_with_perm, institution=self.institution_a, department='Exam')
        for target in (list_url, url):
            with self.subTest(target=target):
                redirected = self.client.get(target)
                self.assertEqual(redirected.status_code, 302)
                self.assertIn(reverse('dashboard'), redirected.url)

    def test_public_admission_pages_carry_no_internal_report_link(self):
        """The public form and the Thank You page stay free of internal reports."""
        response = self.client.get(reverse('public_admission_apply'))
        self.assertEqual(response.status_code, 200)
        for forbidden in (reverse(FUNNEL_PAGE), reverse(FUNNEL_EXPORT),
                          reverse('class_section_summary'), 'admission-funnel'):
            self.assertNotContains(response, forbidden)

        # Source-level guard so the Thank You page (rendered only after a
        # successful public POST) is covered without posting the whole form.
        for template_name in ('students/public_admission_form.html',
                              'students/public_admission_success.html'):
            with self.subTest(template=template_name):
                path = get_template(template_name).origin.name
                with open(path, encoding='utf-8') as handle:
                    source = handle.read()
                for forbidden in ('admission_funnel_report', 'admission_funnel_export',
                                  'class_section_summary', 'admission-funnel'):
                    self.assertNotIn(forbidden, source)
