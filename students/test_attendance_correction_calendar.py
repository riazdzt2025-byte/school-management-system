"""AT-01 / AT-02: attendance correction workflow and monthly calendar.

AT-01 adds a per-record correction page (status/remarks + mandatory reason,
old/new values in the AuditLog), blocks future dates and keeps the existing
institution scoping. AT-02 adds the server-rendered monthly calendar, the
P+A+L rate definition (H excluded, no-record never absent) and the CSV
monthly summary.
"""
from datetime import date, timedelta
from calendar import monthrange

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import (
    AttendanceRecord, AuditLog, Employee, Institution, InstitutionAccess, Student,
)
from .permissions import ensure_default_groups, sync_user_department_permissions


def _today():
    return timezone.localdate()


class AttendanceCorrectionTests(TestCase):
    def setUp(self):
        self.institution = Institution.objects.create(name='Correction School', classes='6,7,9,10')
        self.other = Institution.objects.create(name='Other School', classes='6,7')
        self.student = Student.objects.create(
            institution=self.institution, student_id='C001', name='Correction Student',
            admission_class='6', section='A', admission_year=2026, roll_no=1,
        )
        self.other_student = Student.objects.create(
            institution=self.other, student_id='C002', name='Other Student',
            admission_class='6', section='A', admission_year=2026, roll_no=1,
        )
        self.record = AttendanceRecord.objects.create(
            institution=self.institution, student=self.student,
            date=_today() - timedelta(days=2), status='P', remarks='In class',
        )
        self.other_record = AttendanceRecord.objects.create(
            institution=self.other, student=self.other_student,
            date=_today() - timedelta(days=2), status='A', remarks='Other',
        )
        ensure_default_groups()
        self.user = get_user_model().objects.create_user(username='corrector', password='password')
        self.user.user_permissions.add(Permission.objects.get(codename='change_attendancerecord'))
        self.client.force_login(self.user)

    def test_correction_updates_status_and_writes_audit(self):
        response = self.client.post(reverse('correct_attendance', args=[self.record.pk]), {
            'status': 'A', 'remarks': 'Was absent', 'reason': 'Register corrected after roll call',
        })
        self.assertRedirects(response, reverse('attendance_report'))
        self.record.refresh_from_db()
        self.assertEqual(self.record.status, 'A')
        self.assertEqual(self.record.remarks, 'Was absent')
        log = AuditLog.objects.filter(action='attendance_corrected').last()
        self.assertIsNotNone(log)
        self.assertEqual(log.snapshot['status'], 'P')
        self.assertEqual(log.details['new_status'], 'A')
        self.assertIn('roll call', log.details['reason'])

    def test_reason_is_required(self):
        response = self.client.post(reverse('correct_attendance', args=[self.record.pk]), {
            'status': 'A', 'remarks': 'Changed', 'reason': '',
        })
        self.assertEqual(response.status_code, 200)
        self.record.refresh_from_db()
        self.assertEqual(self.record.status, 'P')
        self.assertContains(response, 'required')

    def test_future_record_cannot_be_corrected(self):
        future = AttendanceRecord.objects.create(
            institution=self.institution, student=self.student,
            date=_today() + timedelta(days=3), status='P',
        )
        response = self.client.post(reverse('correct_attendance', args=[future.pk]), {
            'status': 'A', 'remarks': 'x', 'reason': 'trying ahead of time',
        })
        self.assertEqual(response.status_code, 200)
        future.refresh_from_db()
        self.assertEqual(future.status, 'P')

    def test_cross_institution_record_is_404(self):
        self.client.logout()
        other_user = get_user_model().objects.create_user(username='other-clerk', password='password')
        InstitutionAccess.objects.create(
            user=other_user, institution=self.other, department='Office', is_active=True,
        )
        sync_user_department_permissions(other_user)
        other_user.user_permissions.add(Permission.objects.get(codename='change_attendancerecord'))
        self.client.force_login(other_user)
        response = self.client.post(reverse('correct_attendance', args=[self.record.pk]), {
            'status': 'A', 'remarks': 'x', 'reason': 'cross institution',
        })
        self.assertEqual(response.status_code, 404)
        self.record.refresh_from_db()
        self.assertEqual(self.record.status, 'P')

    def test_user_without_change_permission_is_forbidden(self):
        self.client.logout()
        plain = get_user_model().objects.create_user(username='plain', password='password')
        self.client.force_login(plain)
        response = self.client.post(reverse('correct_attendance', args=[self.record.pk]), {
            'status': 'A', 'remarks': 'x', 'reason': 'no permission',
        })
        self.assertEqual(response.status_code, 403)

    def test_report_shows_correction_link_when_permitted(self):
        response = self.client.get(reverse('attendance_report'))
        self.assertContains(response, reverse('correct_attendance', args=[self.record.pk]))
        self.assertContains(response, 'Correct')

    def test_report_filters_by_status_and_class(self):
        AttendanceRecord.objects.create(
            institution=self.institution, student=self.student,
            date=_today() - timedelta(days=1), status='A',
        )
        response = self.client.get(reverse('attendance_report'), {'status': 'A'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Absent')
        response = self.client.get(reverse('attendance_report'), {'admission_class': '9'})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Correction Student')


class AttendanceCalendarTests(TestCase):
    def setUp(self):
        self.institution = Institution.objects.create(name='Calendar School', classes='6,7,9,10')
        self.other = Institution.objects.create(name='Other Calendar School', classes='6')
        self.student = Student.objects.create(
            institution=self.institution, student_id='CAL001', name='Calendar Student',
            admission_class='6', section='A', admission_year=2026, roll_no=1,
        )
        self.archived = Student.objects.create(
            institution=self.institution, student_id='CAL002', name='Archived Student',
            admission_class='6', section='A', admission_year=2026, roll_no=2,
            is_archived=True, status='DISCONTINUED',
        )
        self.other_student = Student.objects.create(
            institution=self.other, student_id='CAL003', name='Other Calendar Student',
            admission_class='6', section='A', admission_year=2026, roll_no=1,
        )
        self.employee = Employee.objects.create(
            institution=self.institution, name='Calendar Teacher', designation='Teacher',
            join_date=date(2026, 1, 1),
        )
        self.today = _today()
        self.month_start = date(self.today.year, self.today.month, 1)
        self.month_end = date(self.today.year, self.today.month, monthrange(self.today.year, self.today.month)[1])
        # A controlled set: 2 present, 1 absent, 1 late, 1 holiday.
        for offset, status in [(0, 'P'), (1, 'P'), (2, 'A'), (3, 'L'), (4, 'H')]:
            day = self.month_start + timedelta(days=offset)
            if day <= self.month_end:
                AttendanceRecord.objects.create(
                    institution=self.institution, student=self.student,
                    date=day, status=status,
                )
        AttendanceRecord.objects.create(
            institution=self.institution, student=self.archived,
            date=self.month_start, status='P',
        )
        AttendanceRecord.objects.create(
            institution=self.other, student=self.other_student,
            date=self.month_start, status='P',
        )
        AttendanceRecord.objects.create(
            institution=self.institution, employee=self.employee,
            date=self.month_start, status='A',
        )
        self.user = get_user_model().objects.create_superuser(username='calendar-admin', password='password')
        self.client.force_login(self.user)

    def _url(self, **extra):
        params = {'year': self.today.year, 'month': self.today.month}
        params.update(extra)
        return reverse('attendance_calendar') + '?' + '&'.join(f'{k}={v}' for k, v in params.items())

    def test_calendar_page_renders_grid_and_legend(self):
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Attendance Calendar')
        self.assertContains(response, 'No record')
        self.assertContains(response, 'Holiday')
        self.assertContains(response, 'Calendar Student')

    def test_rate_excludes_holiday_and_late_counts_as_attended(self):
        response = self.client.get(self._url())
        # 2P + 1A + 1L + 1H => (2+1)/(2+1+1) = 75.0
        self.assertContains(response, '75.0%')
        self.assertNotContains(response, '80.0%')

    def test_archived_student_is_excluded(self):
        response = self.client.get(self._url())
        self.assertNotContains(response, 'Archived Student')

    def test_other_institution_is_not_shown(self):
        self.client.logout()
        scoped = get_user_model().objects.create_user(username='calendar-scoped', password='password')
        InstitutionAccess.objects.create(
            user=scoped, institution=self.institution, department='Office', is_active=True,
        )
        sync_user_department_permissions(scoped)
        self.client.force_login(scoped)
        response = self.client.get(self._url())
        self.assertNotContains(response, 'Other Calendar Student')

    def test_invalid_month_falls_back_safely(self):
        response = self.client.get(reverse('attendance_calendar'), {'year': 'abc', 'month': '99'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Attendance Calendar')

    def test_month_rollover_navigation(self):
        response = self.client.get(reverse('attendance_calendar'), {'year': 2026, 'month': 12})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'December 2026')
        self.assertContains(response, 'year=2027')
        self.assertContains(response, 'month=1')
        response = self.client.get(reverse('attendance_calendar'), {'year': 2026, 'month': 1})
        self.assertContains(response, 'January 2026')
        self.assertContains(response, 'year=2025')
        self.assertContains(response, 'month=12')

    def test_employee_mode_shows_employee_summary(self):
        response = self.client.get(self._url(mark_type='EMPLOYEE'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Calendar Teacher')

    def test_csv_export_contains_summary_and_rate(self):
        response = self.client.get(reverse('attendance_calendar_export'), {
            'year': self.today.year, 'month': self.today.month,
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/csv', response['Content-Type'])
        body = response.content.decode('utf-8')
        self.assertIn('Calendar Student', body)
        self.assertIn('75.0', body)
        self.assertNotIn('Archived Student', body)

    def test_calendar_links_to_correction_for_a_single_record_day(self):
        day = self.month_start + timedelta(days=6)
        AttendanceRecord.objects.create(
            institution=self.institution, student=self.student,
            date=day, status='P',
        )
        response = self.client.get(self._url())
        self.assertContains(response, reverse('correct_attendance', args=[AttendanceRecord.objects.get(date=day).pk]))


class AttendanceEntryValidationTests(TestCase):
    def setUp(self):
        self.institution = Institution.objects.create(name='Entry School', classes='6,7')
        self.student = Student.objects.create(
            institution=self.institution, student_id='E001', name='Entry Student',
            admission_class='6', section='A', admission_year=2026, roll_no=1,
        )
        ensure_default_groups()
        self.user = get_user_model().objects.create_user(username='entry-clerk', password='password')
        InstitutionAccess.objects.create(
            user=self.user, institution=self.institution, department='Office', is_active=True,
        )
        sync_user_department_permissions(self.user)
        self.client.force_login(self.user)

    def test_future_date_is_rejected(self):
        future = (_today() + timedelta(days=2)).isoformat()
        response = self.client.post(
            reverse('mark_attendance_bulk', kwargs={
                'date_str': future, 'admission_class': '6', 'section': 'A', 'mark_type': 'STUDENT',
            }),
            {f'status_{self.student.id}': 'P'},
        )
        self.assertRedirects(response, reverse('mark_attendance'))
        self.assertFalse(AttendanceRecord.objects.filter(student=self.student).exists())

    def test_invalid_status_is_skipped(self):
        today = _today().isoformat()
        response = self.client.post(
            reverse('mark_attendance_bulk', kwargs={
                'date_str': today, 'admission_class': '6', 'section': 'A', 'mark_type': 'STUDENT',
            }),
            {f'status_{self.student.id}': 'Z'},
        )
        self.assertRedirects(response, reverse('attendance_report'))
        self.assertEqual(AttendanceRecord.objects.count(), 0)

    def test_second_mark_updates_in_place(self):
        today = _today().isoformat()
        url = reverse('mark_attendance_bulk', kwargs={
            'date_str': today, 'admission_class': '6', 'section': 'A', 'mark_type': 'STUDENT',
        })
        self.client.post(url, {f'status_{self.student.id}': 'P'})
        self.client.post(url, {f'status_{self.student.id}': 'A'})
        self.assertEqual(AttendanceRecord.objects.filter(student=self.student).count(), 1)
        self.assertEqual(AttendanceRecord.objects.get(student=self.student).status, 'A')


class AttendanceRateConsistencyTests(TestCase):
    """AT-02: summary, employee detail and calendar share one rate definition."""
    def setUp(self):
        self.institution = Institution.objects.create(name='Rate School', classes='6')
        self.student = Student.objects.create(
            institution=self.institution, student_id='R001', name='Rate Student',
            admission_class='6', section='A', admission_year=2026, roll_no=1,
        )
        self.archived = Student.objects.create(
            institution=self.institution, student_id='R002', name='Archived Rate Student',
            admission_class='6', section='A', admission_year=2026, roll_no=2,
            is_archived=True, status='DISCONTINUED',
        )
        self.employee = Employee.objects.create(
            institution=self.institution, name='Rate Teacher', designation='Teacher',
            join_date=date(2026, 1, 1),
        )
        today = _today()
        for offset, status in [(0, 'P'), (1, 'P'), (2, 'A'), (3, 'L'), (4, 'H')]:
            day = today - timedelta(days=offset)
            AttendanceRecord.objects.create(
                institution=self.institution, student=self.student, date=day, status=status,
            )
            AttendanceRecord.objects.create(
                institution=self.institution, employee=self.employee, date=day, status=status,
            )
        AttendanceRecord.objects.create(
            institution=self.institution, student=self.archived, date=today, status='P',
        )
        self.user = get_user_model().objects.create_superuser(username='rate-admin', password='password')
        self.client.force_login(self.user)

    def test_summary_rate_uses_shared_definition(self):
        response = self.client.get(reverse('attendance_summary'))
        self.assertEqual(response.status_code, 200)
        # 2P + 1A + 1L + 1H => (2+1)/(2+1+1) = 75.0, not 2/5 = 40.0 or 3/5 = 60.0
        self.assertContains(response, '75.0%')
        self.assertNotContains(response, '40.0%')
        self.assertNotContains(response, '60.0%')

    def test_summary_excludes_archived_student(self):
        response = self.client.get(reverse('attendance_summary'))
        self.assertNotContains(response, 'Archived Rate Student')

    def test_employee_detail_rate_uses_shared_definition(self):
        response = self.client.get(reverse('employee_detail', args=[self.employee.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '75.0%')
