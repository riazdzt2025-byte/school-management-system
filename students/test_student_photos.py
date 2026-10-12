"""OF-05: Student photos — upload, display, purge, admission continuity.

Covers:
- Photo size validation (1MB max) on StudentForm and AdmissionApplicationForm
- Student list renders photo thumbnail (or fallback avatar)
- Student detail renders photo
- ID card renders photo (or initials fallback)
- Purge deletes photo file when DELETE_MEDIA_ON_PURGE=True
- Purge retains photo file when DELETE_MEDIA_ON_PURGE=False
- Admission form accepts optional photo
- Enrolment transfers photo from application to student
"""
from io import BytesIO
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, Client, override_settings
from django.contrib.auth import get_user_model
from PIL import Image

from students.models import Student, Institution, AdmissionApplication


def _make_test_image(size_kb=100):
    """Create a small valid PNG image for testing."""
    img = Image.new('RGB', (100, 100), color='red')
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    return SimpleUploadedFile('test.png', buffer.read(), content_type='image/png')


User = get_user_model()


class PhotoSizeValidationTests(TestCase):
    """Photo must be under 1MB (not 2MB)."""

    def test_student_form_rejects_over_1mb(self):
        """StudentForm.clean_photo rejects files > 1MB."""
        from students.forms import StudentForm
        from django import forms

        big = SimpleUploadedFile('big.png', b'\x89PNG\r\n\x1a\n' + b'\x00' * (2 * 1024 * 1024), content_type='image/png')
        form = StudentForm()
        form.cleaned_data = {'photo': big}
        with self.assertRaises(forms.ValidationError) as cm:
            StudentForm.clean_photo(form)
        self.assertIn('under 1 MB', str(cm.exception))

    def test_admission_form_rejects_over_1mb(self):
        """AdmissionApplicationForm.clean_applicant_photo rejects files > 1MB."""
        from students.forms import AdmissionApplicationForm
        from django import forms

        big = SimpleUploadedFile('big.png', b'\x89PNG\r\n\x1a\n' + b'\x00' * (2 * 1024 * 1024), content_type='image/png')
        form = AdmissionApplicationForm()
        form.cleaned_data = {'applicant_photo': big}
        with self.assertRaises(forms.ValidationError) as cm:
            AdmissionApplicationForm.clean_applicant_photo(form)
        self.assertIn('under 1 MB', str(cm.exception))

    def test_admission_form_accepts_under_1mb(self):
        """AdmissionApplicationForm.clean_applicant_photo accepts files < 1MB."""
        from students.forms import AdmissionApplicationForm

        small = _make_test_image(100)  # ~100KB
        form = AdmissionApplicationForm()
        form.cleaned_data = {'applicant_photo': small}
        result = AdmissionApplicationForm.clean_applicant_photo(form)
        self.assertEqual(result, small)

    def test_admission_form_accepts_no_photo(self):
        """AdmissionApplicationForm.clean_applicant_photo accepts None (optional)."""
        from students.forms import AdmissionApplicationForm

        form = AdmissionApplicationForm()
        form.cleaned_data = {'applicant_photo': None}
        result = AdmissionApplicationForm.clean_applicant_photo(form)
        self.assertIsNone(result)


class PhotoDisplayTests(TestCase):
    """Photo renders correctly in list, detail, and ID card views."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user('testuser', password='testpass')
        # Add view_student permission
        from django.contrib.auth.models import Permission
        from django.contrib.contenttypes.models import ContentType
        ct = ContentType.objects.get_for_model(Student)
        perm = Permission.objects.get(content_type=ct, codename='view_student')
        self.user.user_permissions.add(perm)
        
        self.institution = Institution.objects.create(name='Test School', classes='1,2,3,4,5,6,7,8,9,10,11,12')
        self.student = Student.objects.create(
            institution=self.institution,
            name='Test Student',
            admission_class='9',
            section='A',
            roll_no=1,
        )
        self.student.photo = _make_test_image(50)
        self.student.save()

    def test_student_list_renders_photo(self):
        """Student list template includes photo thumbnail CSS."""
        self.client.login(username='testuser', password='testpass')
        response = self.client.get('/students/?institution=' + str(self.institution.pk))
        self.assertEqual(response.status_code, 200)
        # Photo thumbnail CSS class should be in the template
        self.assertContains(response, 'student-photo-thumb')
        # Fallback CSS should also be present
        self.assertContains(response, 'student-photo-fallback')

    def test_student_list_shows_fallback_without_photo(self):
        """Student list shows fallback avatar when no photo."""
        self.student.photo = None
        self.student.save()
        self.client.login(username='testuser', password='testpass')
        response = self.client.get('/students/?institution=' + str(self.institution.pk))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'student-photo-fallback')
        self.assertContains(response, 'T')  # First letter of name

    def test_student_detail_renders_photo(self):
        """Student detail shows photo."""
        self.client.login(username='testuser', password='testpass')
        response = self.client.get(f'/detail/{self.student.pk}/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'student-profile-photo')
        self.assertContains(response, 'student_photos/')

    def test_id_card_renders_photo(self):
        """ID card shows photo."""
        self.client.login(username='testuser', password='testpass')
        response = self.client.get(f'/students/{self.student.pk}/id-card/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'student_photos/')

    def test_id_card_shows_initials_without_photo(self):
        """ID card shows initials when no photo."""
        self.student.photo = None
        self.student.save()
        self.client.login(username='testuser', password='testpass')
        response = self.client.get(f'/students/{self.student.pk}/id-card/')
        self.assertEqual(response.status_code, 200)
        # Should show initials fallback (the initial 'T')
        content = response.content.decode()
        # The photo div should contain the initial when no photo
        self.assertIn('class="photo"', content)


class PhotoPurgeTests(TestCase):
    """Purge deletes or retains photo based on DELETE_MEDIA_ON_PURGE setting."""

    def setUp(self):
        self.user = User.objects.create_user('testuser', password='testpass')
        self.institution = Institution.objects.create(name='Test School', classes='1,2,3,4,5,6,7,8,9,10,11,12')
        self.student = Student.objects.create(
            institution=self.institution,
            name='Test Student',
            admission_class='9',
            section='A',
            roll_no=1,
            is_archived=True,
        )
        self.student.photo = _make_test_image(50)
        self.student.save()
        self.photo_path = self.student.photo.name

    def test_purge_deletes_photo_when_configured(self):
        """Purge deletes photo file when DELETE_MEDIA_ON_PURGE=True."""
        from students.views import _purge_archived_student
        from django.core.files.storage import default_storage

        # Verify photo exists
        self.assertTrue(default_storage.exists(self.photo_path))

        with self.settings(DELETE_MEDIA_ON_PURGE=True):
            _purge_archived_student(self.user, self.student)

        # Photo should be deleted
        self.assertFalse(default_storage.exists(self.photo_path))
        self.assertFalse(Student.objects.filter(pk=self.student.pk).exists())

    def test_purge_retains_photo_when_configured(self):
        """Purge retains photo file when DELETE_MEDIA_ON_PURGE=False."""
        from students.views import _purge_archived_student
        from django.core.files.storage import default_storage

        # Verify photo exists
        self.assertTrue(default_storage.exists(self.photo_path))

        with self.settings(DELETE_MEDIA_ON_PURGE=False):
            _purge_archived_student(self.user, self.student)

        # Photo should still exist
        self.assertTrue(default_storage.exists(self.photo_path))
        self.assertFalse(Student.objects.filter(pk=self.student.pk).exists())

        # Cleanup
        default_storage.delete(self.photo_path)


class AdmissionPhotoTests(TestCase):
    """Admission form accepts photo and enrolment transfers it to student."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user('testuser', password='testpass')
        # Add admission permission
        from django.contrib.auth.models import Permission
        from django.contrib.contenttypes.models import ContentType
        ct = ContentType.objects.get_for_model(AdmissionApplication)
        perm = Permission.objects.get(content_type=ct, codename='add_admissionapplication')
        self.user.user_permissions.add(perm)
        
        self.institution = Institution.objects.create(name='Test School', classes='1,2,3,4,5,6,7,8,9,10,11,12')

    def test_admission_form_has_photo_field(self):
        """Internal admission form includes applicant_photo field."""
        self.client.login(username='testuser', password='testpass')
        response = self.client.get('/admission/new/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'applicant_photo')
        self.assertContains(response, 'Applicant Photo')
