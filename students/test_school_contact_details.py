"""The school's contact details are printed on paper, so they live in one place.

The school and the college each have their own number. The app header shows
both, because it fronts the whole institution; a printed school paper shows the
school's number only, since the college has no part in a school document.
"""
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Exam, Institution, Student, Subject, SubjectRequirement

SCHOOL_PHONE = '01309134783'
COLLEGE_PHONE = '01309135326'


class SchoolContactDetailTests(TestCase):
    def test_settings_hold_both_numbers_and_the_address(self):
        self.assertEqual(settings.SCHOOL_INFO['school_phone'], SCHOOL_PHONE)
        self.assertEqual(settings.SCHOOL_INFO['college_phone'], COLLEGE_PHONE)
        self.assertEqual(settings.SCHOOL_INFO['address'], 'West Rakhalia, Raipur, Lakshmipur-3700')
        # The combined display line keeps both numbers reachable.
        self.assertIn(SCHOOL_PHONE, settings.SCHOOL_INFO['phone'])
        self.assertIn(COLLEGE_PHONE, settings.SCHOOL_INFO['phone'])

    def test_no_template_carries_an_old_number_or_placeholder(self):
        from pathlib import Path
        base = Path(settings.BASE_DIR)
        stale = ('01850790086', '01755881139', '+880 1234-567890', 'Lakshmipur–3711')
        offenders = []
        for folder in (base / 'students' / 'templates', base / 'school_system' / 'templates'):
            for path in folder.rglob('*.html'):
                text = path.read_text(encoding='utf-8')
                for needle in stale:
                    if needle in text:
                        offenders.append(f'{path.name}: {needle}')
        self.assertEqual(offenders, [])


class ContactDetailsOnPagesTests(TestCase):
    def setUp(self):
        self.institution = Institution.objects.create(name='Contact School', classes='6')
        self.user = get_user_model().objects.create_superuser(
            username='contact-admin', password='password',
        )
        self.client.force_login(self.user)
        subject = Subject.objects.create(code='CTC1', name='Contact Paper', full_marks=100)
        SubjectRequirement.objects.create(
            institution=self.institution, admission_class='6',
            subject=subject, requirement_type='MANDATORY',
        )
        self.exam = Exam.objects.create(
            name='Contact Examination-2026', exam_type='FIRST_TERM',
            institution=self.institution, admission_class='6', session='2026',
            is_published=True,
        )
        Student.objects.create(
            institution=self.institution, student_id='CTC001', name='Contact Kid',
            admission_class='6', section='A', roll_no=1, admission_year=2026,
        )

    def test_screen_header_shows_school_and_college_numbers(self):
        html = self.client.get(reverse('dashboard')).content.decode('utf-8')
        self.assertIn(f'School: {SCHOOL_PHONE}', html)
        self.assertIn(f'College: {COLLEGE_PHONE}', html)

    def test_printed_register_masthead_shows_the_school_number_only(self):
        html = self.client.get(reverse('result_sheet', args=[self.exam.pk])).content.decode('utf-8')
        masthead = html.split('class="print-masthead"', 1)[1].split('</header>', 1)[0]
        self.assertIn(SCHOOL_PHONE, masthead)
        self.assertNotIn(COLLEGE_PHONE, masthead)
        self.assertNotIn('College', masthead)
        self.assertIn('Lakshmipur-3700', masthead)
