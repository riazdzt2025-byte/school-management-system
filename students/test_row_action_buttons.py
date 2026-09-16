from html.parser import HTMLParser

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Institution, Student


class StudentListActionMarkupParser(HTMLParser):
    """Collects the checkbox / action-button markup of the student list table."""

    BULK_BUTTON_IDS = ('bulk-update-btn', 'bulk-auto-register-btn', 'bulk-delete-btn')

    def __init__(self):
        super().__init__()
        self.action_buttons = []      # attrs of every element with class "student-action"
        self.action_bars = []         # attrs of every div.student-actions-bar
        self.row_checkboxes = 0       # count of input.row-checkbox
        self.dropdown_toggles = []    # attrs of the per-row "More actions" toggle
        self.bulk_buttons = {}        # id -> attrs
        self.table_header_css = ''

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = (attrs.get('class') or '').split()
        if 'student-action' in classes:
            self.action_buttons.append(attrs)
        if tag == 'div' and 'student-actions-bar' in classes:
            self.action_bars.append(attrs)
        if tag == 'input' and 'row-checkbox' in classes:
            self.row_checkboxes += 1
        if tag == 'button' and 'dropdown-toggle-split' in classes:
            self.dropdown_toggles.append(attrs)
        if tag in ('button', 'input', 'a') and attrs.get('id') in self.BULK_BUTTON_IDS:
            self.bulk_buttons[attrs['id']] = attrs


class StudentRowActionButtonTests(TestCase):
    """Row action buttons must behave like the bulk buttons: disabled until the
    row's checkbox is ticked, re-disabled when unticked."""

    def setUp(self):
        self.institution = Institution.objects.create(name='Row Action School', classes='6,7,8')
        self.user = get_user_model().objects.create_superuser(
            username='row-action-admin', password='password'
        )
        self.client.force_login(self.user)
        self.students = [
            Student.objects.create(
                institution=self.institution,
                student_id=f'RA{i:03d}',
                name=f'Row Action Student {i}',
                admission_class='6',
                section='A',
                admission_year=2026,
            )
            for i in range(3)
        ]

    def get_list_response(self, extra=None):
        params = {'institution': self.institution.pk}
        params.update(extra or {})
        return self.client.get(reverse('student_list'), params)

    def parse(self, response):
        parser = StudentListActionMarkupParser()
        parser.feed(response.content.decode('utf-8'))
        return parser

    # ---- default (no checkbox ticked) state -----------------------------

    def test_every_row_renders_its_action_buttons_locked_by_default(self):
        parser = self.parse(self.get_list_response())

        self.assertEqual(parser.row_checkboxes, 3)
        self.assertEqual(len(parser.action_bars), 3)
        for bar in parser.action_bars:
            self.assertIn('student-actions-locked', (bar.get('class') or '').split())

        # Details / Edit / ID Card / the "More actions" dropdown toggle.
        self.assertGreaterEqual(len(parser.action_buttons), 3 * 4)
        for button in parser.action_buttons:
            self.assertEqual(button.get('aria-disabled'), 'true')

        # The dropdown toggle is a real <button>, so it carries the native
        # disabled attribute until its row is selected.
        self.assertEqual(len(parser.dropdown_toggles), 3)
        for toggle in parser.dropdown_toggles:
            self.assertIn('disabled', toggle)

    def test_marksheet_button_is_locked_too_in_exam_department(self):
        parser = self.parse(self.get_list_response({'department': 'Exam'}))
        marksheet = [
            btn for btn in parser.action_buttons if 'Exam Marks' in (btn.get('title') or '')
        ]
        self.assertEqual(len(marksheet), 3)
        for button in marksheet:
            self.assertEqual(button.get('aria-disabled'), 'true')

    def test_bulk_buttons_stay_disabled_by_default(self):
        parser = self.parse(self.get_list_response())
        self.assertEqual(
            set(parser.bulk_buttons),
            {'bulk-update-btn', 'bulk-auto-register-btn', 'bulk-delete-btn'},
        )
        for button_id, attrs in parser.bulk_buttons.items():
            self.assertIn('disabled', attrs, f'{button_id} must start disabled')

    # ---- the CSS / JS contract that makes "locked" actually block clicks --

    def test_locked_state_css_blocks_pointer_events(self):
        html = self.get_list_response().content.decode('utf-8')
        self.assertIn('student-actions-locked', html)
        self.assertIn('pointer-events: none', html)
        self.assertIn('cursor: not-allowed', html)

    def test_page_loads_the_row_actions_checkbox_tracker(self):
        html = self.get_list_response().content.decode('utf-8')
        self.assertIn('students/js/student_row_actions.js', html)

    # ---- sticky header state from PR #20 must survive ---------------------

    def test_sticky_page_and_table_headers_are_preserved(self):
        html = self.get_list_response().content.decode('utf-8')
        # Top page header (base.html .page-header).
        self.assertIn('position: sticky; top: 0; z-index: 100;', html)
        # Student table column headers (student_list.html .students-table th).
        self.assertIn('position: sticky; top: 0; background: #fff; z-index: 10;', html)
        # Generic table-card header rule from base.html, shared by other pages.
        self.assertIn('position: sticky; top: 0; z-index: 10;', html)
