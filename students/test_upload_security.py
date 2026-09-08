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
