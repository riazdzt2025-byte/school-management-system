"""Regression coverage for student photo validation, display, scoping and cleanup."""
import re
import tempfile
from datetime import timedelta
from io import BytesIO, StringIO
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PIL import Image
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command, CommandError
from django.db import connection, transaction
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from .forms import StudentForm
from .models import (
    Exam, ExamMark, Institution, InstitutionAccess, Student,
    StudentPhotoDeletionJob, Subject, SubjectRequirement,
)
from .photo_deletion import (
    enqueue_student_photo_deletion,
    process_due_student_photo_deletions,
)
from .photo_uploads import (
    PHOTO_MAX_BYTES,
    PHOTO_MAX_DIMENSION,
    PHOTO_MIN_DIMENSION,
    student_photo_upload_to,
    validate_student_photo,
)


def make_png(width=300, height=300, color=(50, 100, 180)):
    output = BytesIO()
    Image.new('RGB', (width, height), color=color).save(output, format='PNG')
    return output.getvalue()


class StudentPhotoPolicyTests(SimpleTestCase):
    def upload_stub(self, *, size=1024, dimensions=(300, 300), name='portrait.png', content_type='image/png'):
        return SimpleNamespace(
            name=name,
            size=size,
            content_type=content_type,
            image=SimpleNamespace(size=dimensions),
        )

    def test_inclusive_minimum_and_maximum_dimensions_are_accepted(self):
        for dimensions in (
            (PHOTO_MIN_DIMENSION, PHOTO_MIN_DIMENSION),
            (PHOTO_MAX_DIMENSION, PHOTO_MAX_DIMENSION),
        ):
            with self.subTest(dimensions=dimensions):
                self.assertIsNone(validate_student_photo(self.upload_stub(dimensions=dimensions)))

    def test_below_minimum_dimensions_are_rejected(self):
        with self.assertRaisesMessage(ValidationError, 'at least'):
            validate_student_photo(self.upload_stub(dimensions=(299, 300)))

    def test_above_maximum_dimensions_are_rejected(self):
        with self.assertRaisesMessage(ValidationError, 'cannot exceed'):
            validate_student_photo(self.upload_stub(dimensions=(4097, 300)))

    def test_photo_larger_than_two_mib_is_rejected(self):
        with self.assertRaisesMessage(ValidationError, '2 MiB'):
            validate_student_photo(self.upload_stub(size=PHOTO_MAX_BYTES + 1))

    def test_all_previously_supported_extensions_remain_allowed(self):
        for extension in ('.jpg', '.jpeg', '.png', '.gif'):
            with self.subTest(extension=extension):
                upload = self.upload_stub(name=f'portrait{extension}')
                self.assertIsNone(validate_student_photo(upload))

    def test_only_supported_extensions_and_image_content_are_accepted(self):
        with self.assertRaisesMessage(ValidationError, 'JPG, PNG or GIF'):
            validate_student_photo(self.upload_stub(name='portrait.svg'))
        with self.assertRaisesMessage(ValidationError, 'not a valid image'):
            validate_student_photo(self.upload_stub(content_type='application/pdf'))

    def test_validator_decodes_real_uploads_without_form_image_metadata(self):
        valid = SimpleUploadedFile(
            'portrait.png', make_png(), content_type='image/png',
        )
        self.assertIsNone(validate_student_photo(valid))

        invalid = SimpleUploadedFile(
            'spoofed.png', b'not an image', content_type='image/png',
        )
        with self.assertRaisesMessage(ValidationError, 'not a valid image'):
            validate_student_photo(invalid)

    def test_upload_path_is_opaque_and_does_not_retain_the_client_filename(self):
        path = student_photo_upload_to(None, '../../student name/portrait.png')
        self.assertRegex(path, re.compile(r'^student_photos/[0-9a-f]{32}\.png$'))
        self.assertNotIn('student name', path)
        self.assertNotIn('..', path)


class StudentPhotoCleanupTests(TestCase):
    def test_successful_on_commit_delete_uses_the_outbox_fast_path(self):
        storage = Mock()
        with patch('students.photo_deletion.storages', {'default': storage}):
            with self.captureOnCommitCallbacks(execute=True):
                job = enqueue_student_photo_deletion('student_photos/example.png')
                storage.delete.assert_not_called()

        storage.delete.assert_called_once_with(job.name)
        self.assertFalse(StudentPhotoDeletionJob.objects.filter(pk=job.pk).exists())

    def test_delete_intent_rolls_back_with_the_database_transaction(self):
        storage = Mock()
        with patch('students.photo_deletion.storages', {'default': storage}):
            with self.assertRaisesRegex(RuntimeError, 'rollback'):
                with transaction.atomic():
                    enqueue_student_photo_deletion('student_photos/example.png')
                    self.assertEqual(StudentPhotoDeletionJob.objects.count(), 1)
                    raise RuntimeError('rollback')

        self.assertEqual(StudentPhotoDeletionJob.objects.count(), 0)
        storage.delete.assert_not_called()

    def test_failed_fast_path_is_retained_and_retried_without_logging_key(self):
        storage = Mock()
        storage.delete.side_effect = OSError('remote storage unavailable: private-name.png')
        attempted_at = timezone.now()

        with patch('students.photo_deletion.storages', {'default': storage}):
            with self.assertLogs('students.photo_deletion', level='ERROR') as captured:
                with self.captureOnCommitCallbacks(execute=True):
                    job = enqueue_student_photo_deletion('student_photos/private-name.png')

            self.assertNotIn('private-name.png', captured.output[0])
            job.refresh_from_db()
            self.assertEqual(job.attempts, 1)
            self.assertEqual(job.last_error_type, 'OSError')
            self.assertEqual(
                job.next_attempt_at,
                job.last_attempt_at + timedelta(seconds=60),
            )

            # Make it due and let the same persisted job succeed on a later run.
            StudentPhotoDeletionJob.objects.filter(pk=job.pk).update(
                next_attempt_at=attempted_at,
            )
            storage.delete.side_effect = None
            result = process_due_student_photo_deletions(now=attempted_at)

        self.assertEqual(result, {'processed': 1, 'deleted': 1, 'retrying': 0})
        self.assertFalse(StudentPhotoDeletionJob.objects.filter(pk=job.pk).exists())

    def test_worker_only_processes_due_jobs_and_honors_batch_limit(self):
        due = enqueue_student_photo_deletion('student_photos/due.png')
        future = enqueue_student_photo_deletion('student_photos/future.png')
        future.next_attempt_at = timezone.now() + timedelta(days=1)
        future.save(update_fields=['next_attempt_at'])
        storage = Mock()

        with patch('students.photo_deletion.storages', {'default': storage}):
            result = process_due_student_photo_deletions(limit=1)

        self.assertEqual(result, {'processed': 1, 'deleted': 1, 'retrying': 0})
        storage.delete.assert_called_once_with(due.name)
        self.assertFalse(StudentPhotoDeletionJob.objects.filter(pk=due.pk).exists())
        self.assertTrue(StudentPhotoDeletionJob.objects.filter(pk=future.pk).exists())

    def test_management_command_reports_retryable_failure_without_exposing_key(self):
        job = enqueue_student_photo_deletion('student_photos/private-name.png')
        storage = Mock()
        storage.delete.side_effect = OSError('backend message with private-name.png')

        with patch('students.photo_deletion.storages', {'default': storage}):
            with self.assertRaisesMessage(CommandError, 'durable retries were scheduled'):
                call_command(
                    'retry_student_photo_deletions',
                    stdout=StringIO(),
                    stderr=StringIO(),
                )

        job.refresh_from_db()
        self.assertEqual(job.attempts, 1)
        self.assertEqual(job.last_error_type, 'OSError')


class StudentPhotoWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.institution = Institution.objects.create(name='Photo Test School', classes='6')
        cls.other_institution = Institution.objects.create(name='Other Photo School', classes='6')
        cls.user = get_user_model().objects.create_superuser(
            'photo-admin', 'photo-admin@example.com', 'password',
        )
        cls.subject = Subject.objects.create(code='PHOTOTEST', name='Photo Test Subject', full_marks=100)
        SubjectRequirement.objects.create(
            institution=cls.institution,
            admission_class='6',
            subject=cls.subject,
            requirement_type='MANDATORY',
        )
        cls.exam = Exam.objects.create(
            name='Photo Test Exam',
            exam_type='FIRST_TERM',
            institution=cls.institution,
            admission_class='6',
            session='2026',
            is_published=True,
        )

    def setUp(self):
        self.media_dir = tempfile.TemporaryDirectory()
        media_settings = override_settings(MEDIA_ROOT=self.media_dir.name, MEDIA_URL='/media/')
        media_settings.enable()
        self.addCleanup(self.media_dir.cleanup)
        self.addCleanup(media_settings.disable)

        self.client.force_login(self.user)
        self.student = self.make_student(
            self.institution, student_id='PHOTO-1', name='Photo Student', roll_no=1,
        )
        self.student.photo.save('portrait.png', ContentFile(make_png()), save=True)
        self.photo_name = self.student.photo.name
        self.storage = self.student.photo.storage
        self.assertTrue(self.storage.exists(self.photo_name))
        ExamMark.objects.create(
            exam=self.exam, student=self.student, subject=self.subject, marks_obtained=82,
        )

    def make_student(self, institution, *, student_id, name, roll_no):
        return Student.objects.create(
            institution=institution,
            student_id=student_id,
            form_no=student_id,
            name=name,
            admission_class='6',
            section='A',
            admission_year=2026,
            roll_no=roll_no,
            gender='M',
            religion='Islam',
            father_name='Guardian',
            guardian_contact_no=f'0180000{roll_no:04d}',
            status='ACTIVE',
        )

    def photo_form_data(self):
        form = StudentForm(instance=self.student, user=self.user)
        data = {}
        for field_name in form.fields:
            if field_name == 'photo':
                continue
            value = form[field_name].value()
            if value not in (None, ''):
                data[field_name] = value
        return data

    def process_photo_deletion_queue(self):
        output = StringIO()
        with patch('students.photo_deletion.storages', {'default': self.storage}):
            call_command(
                'retry_student_photo_deletions',
                stdout=output,
                stderr=StringIO(),
            )
        return output.getvalue()

    def test_photo_is_rendered_on_student_list_detail_and_id_card(self):
        for url in (
            reverse('student_list'),
            reverse('student_detail', args=[self.student.pk]),
            reverse('student_id_card', args=[self.student.pk]),
        ):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, self.photo_name)
                self.assertContains(response, 'Photo Student')
        detail_response = self.client.get(reverse('student_detail', args=[self.student.pk]))
        self.assertContains(detail_response, 'Remove photo')

    def test_photo_is_rendered_on_result_detail_and_both_result_card_surfaces(self):
        urls = (
            reverse('student_result_detail', args=[self.exam.pk, self.student.pk]),
            reverse('result_card', args=[self.exam.pk, self.student.pk]),
            f"{reverse('result_analysis_result_cards')}?exam={self.exam.pk}",
        )
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, self.photo_name)

    def test_missing_photo_uses_accessible_fallback(self):
        other = self.make_student(
            self.institution, student_id='PHOTO-2', name='No Photo Student', roll_no=2,
        )
        response = self.client.get(reverse('student_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No photo for No Photo Student')
        self.assertContains(response, 'No Photo Student')
        detail = self.client.get(reverse('student_detail', args=[other.pk]))
        self.assertContains(detail, 'No photo for No Photo Student')

    def test_saving_other_fields_does_not_query_or_delete_the_existing_photo(self):
        with CaptureQueriesContext(connection) as queries:
            self.student.name = 'Updated Photo Student'
            self.student.save()

        self.assertEqual(len(queries), 1)
        self.assertTrue(self.storage.exists(self.photo_name))

    def test_student_list_does_not_add_a_query_per_photo(self):
        def query_count():
            with CaptureQueriesContext(connection) as queries:
                response = self.client.get(reverse('student_list'))
                self.assertEqual(response.status_code, 200)
            return len(queries)

        one_student_query_count = query_count()
        for number in range(2, 7):
            self.make_student(
                self.institution,
                student_id=f'PHOTO-{number}',
                name=f'List Student {number}',
                roll_no=number,
            )
        several_students_query_count = query_count()
        self.assertEqual(several_students_query_count, one_student_query_count)

    def test_student_form_clear_queues_file_deletion_for_worker(self):
        data = self.photo_form_data()
        data['photo-clear'] = 'on'
        form = StudentForm(data=data, instance=self.student, user=self.user)
        self.assertTrue(form.is_valid(), form.errors)

        saved = form.save()
        saved.refresh_from_db()
        self.assertFalse(saved.photo)
        self.assertTrue(self.storage.exists(self.photo_name))
        self.assertTrue(
            StudentPhotoDeletionJob.objects.filter(name=self.photo_name).exists()
        )

        self.process_photo_deletion_queue()
        self.assertFalse(self.storage.exists(self.photo_name))
        self.assertFalse(
            StudentPhotoDeletionJob.objects.filter(name=self.photo_name).exists()
        )

    def test_replacing_a_photo_queues_old_file_for_worker(self):
        replacement_bytes = make_png(color=(20, 160, 90))
        replacement = SimpleUploadedFile(
            'replacement.png', replacement_bytes, content_type='image/png',
        )
        form = StudentForm(
            data=self.photo_form_data(),
            files={'photo': replacement},
            instance=self.student,
            user=self.user,
        )
        self.assertTrue(form.is_valid(), form.errors)

        saved = form.save()
        saved.refresh_from_db()
        self.assertTrue(saved.photo)
        self.assertNotEqual(saved.photo.name, self.photo_name)
        self.assertTrue(self.storage.exists(saved.photo.name))
        self.assertTrue(self.storage.exists(self.photo_name))
        self.assertTrue(
            StudentPhotoDeletionJob.objects.filter(name=self.photo_name).exists()
        )

        self.process_photo_deletion_queue()
        self.assertFalse(self.storage.exists(self.photo_name))
        self.assertTrue(self.storage.exists(saved.photo.name))

    def test_archiving_retains_photo_and_hard_purge_queues_durable_delete(self):
        response = self.client.post(reverse('delete_student', args=[self.student.pk]))
        self.assertEqual(response.status_code, 302)
        self.student.refresh_from_db()
        self.assertTrue(self.student.is_archived)
        self.assertTrue(self.storage.exists(self.photo_name))

        response = self.client.post(reverse('purge_archived_student', args=[self.student.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Student.objects.filter(pk=self.student.pk).exists())
        self.assertTrue(self.storage.exists(self.photo_name))
        self.assertTrue(
            StudentPhotoDeletionJob.objects.filter(name=self.photo_name).exists()
        )

        self.process_photo_deletion_queue()
        self.assertFalse(self.storage.exists(self.photo_name))
        self.assertFalse(
            StudentPhotoDeletionJob.objects.filter(name=self.photo_name).exists()
        )

    def test_single_photo_clear_remains_available_for_archived_student(self):
        self.student.is_archived = True
        self.student.save(update_fields=['is_archived'])

        response = self.client.post(
            reverse('clear_student_photo', args=[self.student.pk]),
            {'return_to': 'student_detail'},
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Student.objects.get(pk=self.student.pk).is_archived)
        self.assertTrue(self.storage.exists(self.photo_name))
        self.assertTrue(
            StudentPhotoDeletionJob.objects.filter(name=self.photo_name).exists()
        )
        self.process_photo_deletion_queue()
        self.assertFalse(self.storage.exists(self.photo_name))

    def test_bulk_clear_can_clean_archived_students_without_purging_records(self):
        archived = self.make_student(
            self.institution, student_id='PHOTO-ARCHIVED', name='Archived Photo', roll_no=3,
        )
        archived.photo.save('archived.png', ContentFile(make_png()), save=True)
        archived_photo_name = archived.photo.name
        archived.is_archived = True
        archived.save(update_fields=['is_archived'])

        response = self.client.post(reverse('bulk_clear_student_photos'), {
            'student_ids': [str(archived.pk)],
            'institution': str(self.institution.pk),
            'return_to': 'archived_students',
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, f"{reverse('archived_students')}?institution={self.institution.pk}")
        archived.refresh_from_db()
        self.assertTrue(archived.is_archived)
        self.assertFalse(archived.photo)
        self.assertTrue(self.storage.exists(archived_photo_name))
        self.assertTrue(
            StudentPhotoDeletionJob.objects.filter(name=archived_photo_name).exists()
        )
        self.process_photo_deletion_queue()
        self.assertFalse(self.storage.exists(archived_photo_name))

    def test_single_photo_clear_is_institution_scoped(self):
        foreign = self.make_student(
            self.other_institution, student_id='PHOTO-FOREIGN-SINGLE',
            name='Foreign Single Photo', roll_no=1,
        )
        foreign.photo.save('foreign-single.png', ContentFile(make_png()), save=True)
        foreign_photo_name = foreign.photo.name
        clerk = get_user_model().objects.create_user('photo-single-clerk', password='password')
        clerk.user_permissions.add(Permission.objects.get(codename='change_student'))
        InstitutionAccess.objects.create(
            user=clerk, institution=self.institution, department='Office',
        )
        self.client.force_login(clerk)

        response = self.client.post(reverse('clear_student_photo', args=[foreign.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(self.storage.exists(foreign_photo_name))

    def test_bulk_clear_is_scoped_and_rejects_a_mixed_cross_institution_batch(self):
        foreign_student = self.make_student(
            self.other_institution,
            student_id='PHOTO-FOREIGN',
            name='Foreign Photo Student',
            roll_no=1,
        )
        foreign_student.photo.save('foreign.png', ContentFile(make_png()), save=True)
        foreign_photo_name = foreign_student.photo.name

        clerk = get_user_model().objects.create_user('photo-clerk', password='password')
        clerk.user_permissions.add(Permission.objects.get(codename='change_student'))
        InstitutionAccess.objects.create(
            user=clerk, institution=self.institution, department='Office',
        )
        self.client.force_login(clerk)

        response = self.client.post(reverse('bulk_clear_student_photos'), {
            'student_ids': [str(self.student.pk), str(foreign_student.pk)],
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(self.storage.exists(self.photo_name))
        self.assertTrue(self.storage.exists(foreign_photo_name))

        response = self.client.post(reverse('bulk_clear_student_photos'), {
            'student_ids': [str(self.student.pk)],
        })
        self.assertEqual(response.status_code, 302)
        self.student.refresh_from_db()
        self.assertFalse(self.student.photo)
        self.assertTrue(self.storage.exists(self.photo_name))
        self.assertTrue(self.storage.exists(foreign_photo_name))
        self.process_photo_deletion_queue()
        self.assertFalse(self.storage.exists(self.photo_name))
        self.assertTrue(self.storage.exists(foreign_photo_name))

    def test_bulk_clear_requires_change_permission(self):
        viewer = get_user_model().objects.create_user('photo-viewer', password='password')
        viewer.user_permissions.add(Permission.objects.get(codename='view_student'))
        self.client.force_login(viewer)
        response = self.client.post(reverse('bulk_clear_student_photos'), {
            'student_ids': [str(self.student.pk)],
        })
        self.assertEqual(response.status_code, 403)
        self.assertTrue(self.storage.exists(self.photo_name))
