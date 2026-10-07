"""Regression tests for upload security (P0 security audit session).
Covers model-field photo validation and Excel import validation
(ExcelImportForm / ExamExcelImportForm.clean_excel_file).
Does NOT restore SSC features (session rule 4).
"""
from django import forms
from django.test import TestCase, Client
from django.core.files.uploadedfile import SimpleUploadedFile
from students.forms import StudentForm, ExcelImportForm, ExamExcelImportForm
from students.photo_uploads import validate_student_photo


class PhotoUploadSecurityTests(TestCase):
    def test_photo_too_large_rejected(self):
        big = SimpleUploadedFile('big.png', b'x' * (3 * 1024 * 1024), content_type='image/png')
        with self.assertRaises(forms.ValidationError) as cm:
            validate_student_photo(big)
        self.assertIn('2 MiB', str(cm.exception))

    def test_photo_bad_extension_rejected(self):
        bad = SimpleUploadedFile('shell.php', b'<?php echo 1; ?>', content_type='image/png')
        with self.assertRaises(forms.ValidationError) as cm:
            validate_student_photo(bad)
        self.assertIn('JPG', str(cm.exception))

    def test_photo_non_image_content_rejected(self):
        bad = SimpleUploadedFile('fake.jpg', b'not an image', content_type='application/pdf')
        with self.assertRaises(forms.ValidationError) as cm:
            validate_student_photo(bad)
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

    def _png(self, width, height):
        from io import BytesIO
        from PIL import Image

        image_buffer = BytesIO()
        Image.new('RGB', (width, height), color='white').save(image_buffer, format='PNG')
        return image_buffer.getvalue()

    def test_photo_below_minimum_dimensions_rejected_end_to_end(self):
        photo = SimpleUploadedFile('photo.png', self._png(299, 300), content_type='image/png')
        form = StudentForm(data=self._valid_student_data(), files={'photo': photo})
        self.assertFalse(form.is_valid())
        self.assertIn('at least 300', str(form.errors['photo']))

    def test_photo_above_maximum_dimensions_rejected_end_to_end(self):
        photo = SimpleUploadedFile('photo.png', self._png(4097, 300), content_type='image/png')
        form = StudentForm(data=self._valid_student_data(), files={'photo': photo})
        self.assertFalse(form.is_valid())
        self.assertIn('cannot exceed 4096', str(form.errors['photo']))

    def test_real_minimum_size_image_accepted_end_to_end(self):
        """A genuine minimum-size PNG passes the complete StudentForm."""
        photo = SimpleUploadedFile('photo.png', self._png(300, 300), content_type='image/png')
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
