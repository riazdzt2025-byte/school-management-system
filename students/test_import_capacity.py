"""Tests for P1-7: Excel student import honours SectionCapacity.

A row that would push a class/section past its configured capacity must be
skipped (not created), matching the Add Student form. If no capacity row exists
the section is unrestricted.
"""
import io

import openpyxl
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from .models import Institution, SectionCapacity, Student


class ImportCapacityTests(TestCase):
    def setUp(self):
        self.institution = Institution.objects.create(
            name='School', classes='6',
        )
        self.user = get_user_model().objects.create_user(
            username='office', password='password',
        )
        self.user.user_permissions.add(
            Permission.objects.get(codename='add_student')
        )
        self.client.force_login(self.user)
        # Fill section 6/A to its limit (capacity 1).
        SectionCapacity.objects.create(
            institution=self.institution, admission_class='6', section='A',
            capacity=1,
        )
        Student.objects.create(
            institution=self.institution, student_id='S001', name='Seat One',
            admission_class='6', section='A', admission_year=2026, roll_no=1,
            gender='M', religion='Islam',
        )

    def _make_sheet(self, rows):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(['Institution', 'Name', 'Admission Class', 'Section',
                   'Admission Year', 'Roll No', 'Gender', 'Religion',
                   "Father's Name", 'Contact No', 'Guardian Contact No', 'Group'])
        for row in rows:
            ws.append(row)
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return SimpleUploadedFile(
            'students.xlsx', buf.read(),
            content_type=('application/vnd.openxmlformats-officedocument'
                          '.spreadsheetml.sheet'),
        )

    def test_full_section_row_is_skipped(self):
        # One seat is already taken; a second row for 6/A must not be created.
        f = self._make_sheet([
            [self.institution.name, 'Seat Two', '6', 'A', 2026, 2,
             'Male', 'Islam', 'F', '01700000000', '01800000000', 'Non-Group'],
        ])
        before = Student.objects.count()
        response = self.client.post(
            reverse('import_students'), {'excel_file': f},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Student.objects.count(), before)
        self.assertFalse(Student.objects.filter(name='Seat Two').exists())

    def test_room_available_row_is_created(self):
        # A different section (no capacity row) is unrestricted.
        f = self._make_sheet([
            [self.institution.name, 'Seat Two', '6', 'B', 2026, 2,
             'Male', 'Islam', 'F', '01700000000', '01800000000', 'Non-Group'],
        ])
        response = self.client.post(
            reverse('import_students'), {'excel_file': f},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Student.objects.filter(name='Seat Two', section='B').exists())
