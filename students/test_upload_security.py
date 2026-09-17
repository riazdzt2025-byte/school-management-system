"""Regression tests for upload security (P0 security audit session).
Covers photo validation (StudentForm.clean_photo) and Excel import
validation (ExcelImportForm / ExamExcelImportForm.clean_excel_file).
Does NOT restore SSC features (session rule 4).
"""
from django import forms
from django.test import TestCase, Client
from django.core.files.uploadedfile import SimpleUploadedFile
from students.forms import StudentForm, ExcelImportForm, ExamExcelImportForm


class PhotoUploadSecurityTests(TestCase):
    def test_photo_too_large_rejected(self):
        big = SimpleUploadedFile('big.png', b'\x89PNG\r\n\x1a\n' + b'\x00' * (3 * 1024 * 1024), content_type='image/png')
        form = StudentForm()
        form.cleaned_data = {'photo': big}
        with self.assertRaises(forms.ValidationError) as cm:
            StudentForm.clean_photo(form)
        self.assertIn('under 2 MB', str(cm.exception))

    def test_photo_bad_extension_rejected(self):
        bad = SimpleUploadedFile('shell.php', b'<?php echo 1; ?>', content_type='image/png')
        form = StudentForm()
        form.cleaned_data = {'photo': bad}
        with self.assertRaises(forms.ValidationError) as cm:
            StudentForm.clean_photo(form)
        self.assertIn('JPG', str(cm.exception) or 'Only')

    def test_photo_non_image_content_rejected(self):
        bad = SimpleUploadedFile('fake.jpg', b'not an image', content_type='application/pdf')
        form = StudentForm()
        form.cleaned_data = {'photo': bad}
        with self.assertRaises(forms.ValidationError) as cm:
            StudentForm.clean_photo(form)
        self.assertIn('not a valid image', str(cm.exception))


class PhotoEndToEndValidationTests(TestCase):
    """Full-form proof that content spoofing is rejected, not merely the
    extension/content-type: the field-level Pillow verification that stands
    between an upload and MEDIA_ROOT must stay wired (regression lock for the
    sensitive-upload audit, SEC session-02)."""

    def _valid_student_data(self):
        return {
            'name': 'Upload Student', 'admission_class': '6', 'section': 'A',
            'admission_year': '2026', 'roll_no': '1', 'gender': 'M',
            'religion': 'Islam', 'guardian_contact_no': '01812340000',
            'status': 'ACTIVE',
        }

    def test_fake_image_content_rejected_end_to_end(self):
        """Bytes that are not an image, masquerading as image/jpeg, are refused
        even with a .jpg name and image content-type."""
        fake = SimpleUploadedFile('photo.jpg', b'not actually a jpeg <script>alert(1)</script>',
                                  content_type='image/jpeg')
        form = StudentForm(data=self._valid_student_data(), files={'photo': fake})
        self.assertFalse(form.is_valid())
        self.assertIn('photo', form.errors)

    def test_svg_rejected_end_to_end(self):
        """SVG is script-capable markup, so it is outside the allowed extension
        set even though browsers can render it as an image."""
        svg = SimpleUploadedFile('vector.svg', b'<svg xmlns="http://www.w3.org/2000/svg"></svg>',
                                 content_type='image/svg+xml')
        form = StudentForm(data=self._valid_student_data(), files={'photo': svg})
        self.assertFalse(form.is_valid())
        self.assertIn('photo', form.errors)

    def test_real_small_image_accepted_end_to_end(self):
        """The legitimate path keeps working: a genuine tiny PNG passes the
        full form (guardian contact is the only other required value here)."""
        import base64
        png_bytes = base64.b64decode(
            'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=='
        )
        photo = SimpleUploadedFile('photo.png', png_bytes, content_type='image/png')
        form = StudentForm(data=self._valid_student_data(), files={'photo': photo})
        self.assertTrue(form.is_valid(), form.errors)


class ExcelImportSecurityTests(TestCase):
    def test_excel_too_large_rejected(self):
        big = SimpleUploadedFile('big.xlsx', b'PK' + b'\x00' * (11 * 1024 * 1024), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        form = ExcelImportForm(data={}, files={'excel_file': big})
        # Direct clean call
        form2 = ExcelImportForm()
        form2.cleaned_data = {'excel_file': big}
        with self.assertRaises(forms.ValidationError) as cm:
            ExcelImportForm.clean_excel_file(form2)
        self.assertIn('under 10 MB', str(cm.exception))

    def test_excel_wrong_extension_rejected(self):
        bad = SimpleUploadedFile('bad.xls', b'fake', content_type='application/vnd.ms-excel')
        form = ExamExcelImportForm()
        form.cleaned_data = {'excel_file': bad}
        with self.assertRaises(forms.ValidationError) as cm:
            ExamExcelImportForm.clean_excel_file(form)
        self.assertIn('.xlsx', str(cm.exception))

    def test_student_import_rejects_non_xlsx_extension(self):
        bad = SimpleUploadedFile('evil.html', b'<html></html>', content_type='text/html')
        form = ExcelImportForm()
        form.cleaned_data = {'excel_file': bad}
        with self.assertRaises(forms.ValidationError) as cm:
            ExcelImportForm.clean_excel_file(form)
        self.assertIn('.xlsx', str(cm.exception))

    def test_marks_excel_too_large_rejected(self):
        big = SimpleUploadedFile('big.xlsx', b'PK' + b'\x00' * (11 * 1024 * 1024), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        form = ExamExcelImportForm()
        form.cleaned_data = {'excel_file': big}
        with self.assertRaises(forms.ValidationError) as cm:
            ExamExcelImportForm.clean_excel_file(form)
        self.assertIn('under 10 MB', str(cm.exception))
