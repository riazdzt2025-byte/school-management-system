"""Result pages must not issue a settings query for every student/subject cell.

The small and large cohorts use the same subjects and mark distribution.  Their
SQL query counts must stay constant as the cohort grows.  These are synthetic
fixtures only; no production database or live service is involved.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from .models import (
    Exam, ExamMark, Institution, Student, Subject, SubjectMarkSetting,
    SubjectRequirement,
)
from .result_utils import build_exam_results, get_subject_marks


class ResultPerformanceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.institution = Institution.objects.create(name='Performance School', classes='9')
        cls.admin = get_user_model().objects.create_superuser(
            'result-performance-admin', 'performance@example.invalid', 'password',
        )
        cls.subjects = [
            Subject.objects.create(code=f'P{index:02}', name=f'Paper {index}', full_marks=100)
            for index in range(10)
        ]
        for subject in cls.subjects:
            SubjectRequirement.objects.create(
                institution=cls.institution, admission_class='9', subject=subject,
                requirement_type='MANDATORY',
            )
            SubjectMarkSetting.objects.create(
                institution=cls.institution, admission_class='9', subject=subject,
                exam_type='FIRST_TERM', full_marks=50, cq_marks=30, mcq_marks=20,
            )
        cls.small_exam = cls.make_cohort('A', 8)
        cls.large_exam = cls.make_cohort('B', 80)

    @classmethod
    def make_cohort(cls, section, count):
        exam = Exam.objects.create(
            name=f'First Term {section}', exam_type='FIRST_TERM',
            institution=cls.institution, admission_class='9', section=section,
            session='2026', is_published=True,
        )
        students = Student.objects.bulk_create([
            Student(
                institution=cls.institution, student_id=f'PERF-{section}-{index:03}',
                name=f'Student {section} {index:03}', admission_class='9',
                section=section, roll_no=index, admission_year=2026,
            )
            for index in range(1, count + 1)
        ])
        ExamMark.objects.bulk_create([
            ExamMark(
                exam=exam, student=student, subject=subject,
                cq_obtained=24, mcq_obtained=16, marks_obtained=40,
            )
            for student in students for subject in cls.subjects
        ])
        return exam

    def assert_constant_queries(self, callback, limit):
        with CaptureQueriesContext(connection) as small:
            small_result = callback(self.small_exam)
        with CaptureQueriesContext(connection) as large:
            large_result = callback(self.large_exam)
        self.assertEqual(
            len(small), len(large),
            f'Queries grew with cohort: 8 students={len(small)}, 80={len(large)}',
        )
        self.assertLessEqual(len(large), limit)
        return small_result, large_result

    def test_builder_query_count_does_not_grow_with_student_count(self):
        def calculate(exam):
            columns, results = build_exam_results(exam)
            self.assertEqual(len(columns), 10)
            self.assertEqual(results[0]['gpa'], Decimal('5.00'))
            self.assertEqual(results[0]['total_obtained'], Decimal('400'))
            self.assertEqual(results[0]['total_full'], Decimal('500'))
            return len(results)
        self.assertEqual(self.assert_constant_queries(calculate, 15), (8, 80))

    def test_official_result_surfaces_have_bounded_queries(self):
        surfaces = [
            ('result_sheet', {}),
            ('result_sheet', {'print': '1'}),
            ('exam_result_summary', {}),
            ('full_rank_list', {}),
            ('top_10', {}),
            ('result_analysis_subject_fail', {}),
            ('result_analysis_result_cards', {}),
            ('result_analysis_merit_slides', {}),
        ]
        for name, extra in surfaces:
            with self.subTest(surface=name, params=extra):
                def load(exam):
                    url = reverse(name) if name.startswith('result_analysis_') else reverse(name, args=[exam.pk])
                    params = {'exam': exam.pk} if name.startswith('result_analysis_') else {}
                    response = self.client.get(url, {**params, **extra})
                    self.assertEqual(response.status_code, 200)
                    return response
                self.assert_constant_queries(load, 40)

    def test_individual_result_surfaces_have_bounded_queries(self):
        for name in ('student_result_detail', 'result_card'):
            with self.subTest(surface=name):
                def load(exam):
                    student = Student.objects.filter(exam_marks__exam=exam).order_by('roll_no').first()
                    response = self.client.get(reverse(name, args=[exam.pk, student.pk]))
                    self.assertEqual(response.status_code, 200)
                    return response
                # One extra lookup for the requested student, independent of cohort size.
                self.assert_constant_queries(load, 25)

    def test_provisional_query_count_does_not_grow_with_student_count(self):
        # An entirely unentered paper must not reintroduce per-cell lookups.
        ExamMark.objects.filter(subject=self.subjects[-1]).delete()
        def load(exam):
            response = self.client.get(reverse('result_provisional', args=[exam.pk]))
            self.assertEqual(response.status_code, 200)
            self.assertTrue(all(row['status'] == 'Pending' for row in response.context['results']))
            return response
        self.assert_constant_queries(load, 30)

    def test_edited_marks_and_settings_are_visible_on_the_next_calculation(self):
        _columns, before = build_exam_results(self.small_exam)
        self.assertEqual(before[0]['status'], 'Pass')
        mark = ExamMark.objects.filter(
            exam=self.small_exam, student=before[0]['student'], subject=self.subjects[0],
        )
        mark.update(cq_obtained=0, mcq_obtained=10, marks_obtained=10)
        _columns, after = build_exam_results(self.small_exam)
        row = next(row for row in after if row['student'].pk == before[0]['student'].pk)
        self.assertEqual(row['status'], 'Fail')
        self.assertEqual(row['subject_results'][0]['full'], 50)
        SubjectMarkSetting.objects.filter(
            institution=self.institution, admission_class='9', subject=self.subjects[0],
            exam_type='FIRST_TERM',
        ).update(full_marks=100, cq_marks=60, mcq_marks=40)
        _columns, updated = build_exam_results(self.small_exam)
        row = next(row for row in updated if row['student'].pk == before[0]['student'].pk)
        self.assertEqual(row['subject_results'][0]['full'], 100)
        self.assertEqual(row['subject_results'][0]['pass_marks'], 40)

    def test_bulk_settings_match_single_lookup_priority_and_isolation(self):
        from .result_utils import get_subject_marks_map

        other = Institution.objects.create(name='Other Performance School', classes='9')
        physics = self.subjects[0]
        # Group wins over class spelling; exact class wins over the alternate
        # spelling; a blank group is only a fallback.  None of other school's
        # settings may leak into this exam.
        settings = [
            ('9', '', 51), ('09', '', 52), ('9', 'SCI', 53),
            ('09', 'SCI', 54), ('9', 'BUS', 55),
        ]
        for admission_class, group, full_marks in settings:
            SubjectMarkSetting.objects.create(
                institution=self.institution, admission_class=admission_class,
                subject=physics, exam_type='FINAL_TERM', group=group,
                full_marks=full_marks,
            )
        SubjectMarkSetting.objects.create(
            institution=other, admission_class='9', subject=physics,
            exam_type='FIRST_TERM', group='SCI', full_marks=99,
        )
        for exam_type in ('FIRST_TERM', 'FINAL_TERM'):
            self.small_exam.exam_type = exam_type
            for group in ('', 'SCI', 'BUS', 'HUM'):
                expected = {
                    subject.pk: get_subject_marks(self.small_exam, subject, group=group)
                    for subject in self.subjects
                }
                with CaptureQueriesContext(connection) as bulk:
                    actual = get_subject_marks_map(self.small_exam, self.subjects, group=group)
                self.assertEqual(len(bulk), 1)
                self.assertEqual(
                    {pk: config.pk for pk, config in actual.items()},
                    {pk: config.pk for pk, config in expected.items()},
                )
                self.assertEqual(actual[physics.pk].full_marks, expected[physics.pk].full_marks)

    def test_bulk_settings_keep_subject_defaults_when_no_override_exists(self):
        from .result_utils import get_subject_marks_map
        SubjectMarkSetting.objects.all().delete()
        configs = get_subject_marks_map(self.small_exam, self.subjects)
        self.assertEqual({pk: config.pk for pk, config in configs.items()},
                         {subject.pk: subject.pk for subject in self.subjects})
        self.assertTrue(all(config.full_marks == 100 for config in configs.values()))
        self.assertEqual(get_subject_marks_map(self.small_exam, []), {})

    def test_result_layout_loads_local_nonblocking_vendor_assets(self):
        from django.contrib.staticfiles import finders
        from html.parser import HTMLParser

        class Assets(HTMLParser):
            def __init__(self):
                super().__init__()
                self.stylesheets = []
                self.scripts = []

            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                if tag == 'link' and attrs.get('rel') == 'stylesheet':
                    self.stylesheets.append(attrs.get('href', ''))
                if tag == 'script' and attrs.get('src'):
                    self.scripts.append(attrs)

        response = self.client.get(reverse('result_sheet', args=[self.small_exam.pk]))
        parser = Assets()
        parser.feed(response.content.decode())
        self.assertEqual(len(parser.stylesheets), 3)
        self.assertTrue(all(url.startswith('/static/students/vendor/') for url in parser.stylesheets))
        for url in parser.stylesheets:
            self.assertIsNotNone(finders.find(url.removeprefix('/static/')), url)
        bootstrap = next(item for item in parser.scripts if 'bootstrap.bundle' in item['src'])
        self.assertIn('defer', bootstrap)
        self.assertTrue(bootstrap['src'].startswith('/static/'))
        for path in (
            'students/vendor/bootstrap/LICENSE',
            'students/vendor/bootstrap-icons/LICENSE',
            'students/vendor/fonts/Inter-LICENSE',
            'students/vendor/fonts/Fraunces-LICENSE',
        ):
            self.assertIsNotNone(finders.find(path), path)
        # No external stylesheet/font/CDN request can hold the table hostage.
        self.assertNotIn('fonts.googleapis.com', response.content.decode())
        self.assertNotIn('cdnjs.cloudflare.com', response.content.decode())

    def test_login_and_student_detail_do_not_add_blocking_cdn_assets(self):
        from html.parser import HTMLParser

        class Assets(HTMLParser):
            def __init__(self):
                super().__init__()
                self.stylesheets = []
                self.scripts = []

            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                if tag == 'link' and attrs.get('rel') == 'stylesheet':
                    self.stylesheets.append(attrs.get('href', ''))
                if tag == 'script' and attrs.get('src'):
                    self.scripts.append(attrs)

        student = Student.objects.filter(exam_marks__exam=self.small_exam).first()
        detail = self.client.get(reverse('student_detail', args=[student.pk]))
        self.assertEqual(detail.status_code, 200)
        parser = Assets()
        parser.feed(detail.content.decode())
        # The profile's Results tab must reuse base.html's single deferred
        # bundle, not download Bootstrap a second time from a CDN.
        bundles = [item for item in parser.scripts if 'bootstrap.bundle' in item['src']]
        self.assertEqual(len(bundles), 1)
        self.assertIn('defer', bundles[0])
        self.assertTrue(all(url.startswith('/static/') for url in parser.stylesheets))
        self.assertNotIn('cdnjs.cloudflare.com', detail.content.decode())

        self.client.logout()
        login = self.client.get(reverse('login'))
        self.assertEqual(login.status_code, 200)
        parser = Assets()
        parser.feed(login.content.decode())
        self.assertEqual(len(parser.stylesheets), 1)
        self.assertTrue(parser.stylesheets[0].startswith('/static/students/vendor/'))
        self.assertNotIn('cdnjs.cloudflare.com', login.content.decode())

    def test_production_static_manifest_includes_fonts_and_source_maps(self):
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        from django.core.management import call_command
        from django.test import override_settings
        from whitenoise.storage import CompressedManifestStaticFilesStorage

        # Exercise the exact production backend directly; another test may have
        # already initialized Django's lazy default staticfiles_storage.
        with TemporaryDirectory() as root, override_settings(STATIC_ROOT=root, DEBUG=False):
            storage = CompressedManifestStaticFilesStorage()
            with patch('django.contrib.staticfiles.management.commands.collectstatic.staticfiles_storage', storage):
                call_command('collectstatic', interactive=False, verbosity=0)
            for path in (
                'students/vendor/bootstrap/css/bootstrap.min.css',
                'students/vendor/bootstrap/js/bootstrap.bundle.min.js',
                'students/vendor/fonts/fonts.css',
                'students/vendor/fonts/files/inter-latin-400-normal.woff2',
                'students/vendor/bootstrap-icons/fonts/bootstrap-icons.woff2',
            ):
                self.assertTrue(storage.exists(path), path)
                self.assertNotEqual(storage.url(path), '/static/' + path)
            # Resolve the final URL-rewritten file via the manifest. hashing
            # the unmodified original would miss the rewritten font URLs.
            hashed = storage.stored_name('students/vendor/fonts/fonts.css')
            with storage.open(hashed) as source:
                css = source.read().decode()
            self.assertRegex(css, r'inter-latin-400-normal\.[0-9a-f]{12}\.woff2')
            self.assertNotIn("url('files/inter-latin-400-normal.woff2')", css)

    def setUp(self):
        self.client.force_login(self.admin)
