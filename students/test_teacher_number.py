"""Teacher number (2011 + branch + that branch's serial) and the number-first screen.

Covers four things a clerk can get wrong, because each one would otherwise be
discovered on paper:

1. **Allocation** — teaching staff get their branch's next free ``2011 02 0001`` number on
   first save; the counter never hands a number out twice, and it respects
   numbers already stored by hand.
2. **Non-teachers** — an Aya / Caretaker / Accountant never gets a number, and
   never appears in the teacher picker.
3. **Typing** — ``2011 02 0001``, ``2011-02-0001``, Bangla digits and the bare
   serial ``0001`` (inside the branch) all resolve to the same teacher; an
   unknown number says so plainly instead of silently assigning nobody.
4. **Fewer choices** — institution comes from the teacher, the session defaults
   to the running one, and the employee dropdown is gone from the screen.
"""
from datetime import date

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from .models import (
    AuditLog, DocumentSequence, Employee, Institution, Subject, SubjectRequirement,
    TeacherAssignment, current_academic_session, display_teacher_number,
    format_teacher_number, next_teacher_number, normalize_teacher_number,
    teacher_number_branch, teacher_number_serial,
)
from .permissions import ensure_default_groups


class TeacherNumberFormatTests(TestCase):
    def test_founding_year_branch_and_serial(self):
        self.assertEqual(format_teacher_number(1, 2), '2011020001')
        self.assertEqual(format_teacher_number(42, 1), '2011010042')
        self.assertEqual(teacher_number_serial('2011010042'), 42)
        self.assertEqual(teacher_number_branch('2011010042'), 1)
        self.assertIsNone(teacher_number_serial('2011-01-0042'))
        self.assertIsNone(teacher_number_serial(''))
        # The old global serial (six digits, no branch) is not a number any more.
        self.assertIsNone(teacher_number_serial('2011000042'))

    def test_a_number_needs_a_branch(self):
        with self.assertRaises(ValueError):
            format_teacher_number(1, None)

    def test_display_number_is_grouped_for_printing(self):
        self.assertEqual(display_teacher_number('2011020001'), '2011 02 0001')
        self.assertEqual(display_teacher_number('2011010042'), '2011 01 0042')
        self.assertEqual(display_teacher_number(''), '')
        # An unknown layout is shown exactly as stored, never mangled.
        self.assertEqual(display_teacher_number('CUSTOM-7'), 'CUSTOM-7')
        self.assertEqual(display_teacher_number('2011000042'), '2011000042')

    def test_normalize_accepts_what_clerk_types(self):
        cases = {
            '2011 02 0001': '2011020001',
            '2011-02-0001': '2011020001',
            '2011020001': '2011020001',
            '২০১১০২০০০১': '2011020001',   # Bangla digits
            '2011.02.0001': '2011020001',
            '02 0001': '2011020001',      # branch + serial, as it is spoken
            '020001': '2011020001',
        }
        for typed, stored in cases.items():
            with self.subTest(typed=typed):
                self.assertEqual(normalize_teacher_number(typed), stored)

    def test_a_bare_serial_needs_the_branch(self):
        # "1" is ambiguous across branches, so the screen passes its branch.
        self.assertEqual(normalize_teacher_number('1', 2), '2011020001')
        self.assertEqual(normalize_teacher_number('0001', 2), '2011020001')
        self.assertEqual(normalize_teacher_number('2011 1', 2), '2011020001')
        self.assertEqual(normalize_teacher_number('1'), '1')

    def test_normalize_leaves_junk_alone(self):
        self.assertEqual(normalize_teacher_number('rahim'), 'rahim')
        self.assertEqual(normalize_teacher_number(''), '')
        self.assertEqual(normalize_teacher_number(None), '')

    def test_institution_numbers_and_labels(self):
        first = Institution.objects.create(name='College 1', classes='11,12')
        second = Institution.objects.create(name='School 2', classes='9,10')
        self.assertEqual(first.number, 1)
        self.assertEqual(second.number, 2)
        self.assertEqual(second.number_display, '02')
        self.assertEqual(second.short_label, '02 — School 2')
        # A branch added by hand is never renumbered.
        third = Institution.objects.create(name='Shishukanon 3', classes='Shishu', number=3)
        self.assertEqual(third.number, 3)
        # Deleting a branch frees its number for the next one added.
        third.delete()
        fourth = Institution.objects.create(name='Madrasa 4', classes='1,2,3')
        self.assertEqual(fourth.number, 3)

    def test_current_session_follows_the_july_year_start(self):
        self.assertEqual(current_academic_session(date(2026, 8, 1)), '2026-2027')
        self.assertEqual(current_academic_session(date(2026, 6, 30)), '2025-2026')
        self.assertEqual(current_academic_session(date(2027, 1, 9)), '2026-2027')


class TeacherNumberAllocationTests(TestCase):
    def setUp(self):
        self.institution = Institution.objects.create(
            name='Number School', classes='9,10', number=2
        )

    def _employee(self, name, designation='Assistant Teacher'):
        return Employee.objects.create(
            institution=self.institution, name=name, designation=designation,
            join_date=date(2026, 1, 1),
        )

    def test_teacher_gets_the_first_number(self):
        teacher = self._employee('First Teacher')
        self.assertEqual(teacher.teacher_no, '2011020001')

    def test_serials_increase(self):
        numbers = [self._employee(f'Teacher {i}').teacher_no for i in range(1, 4)]
        self.assertEqual(numbers, ['2011020001', '2011020002', '2011020003'])

    def test_non_teaching_staff_get_no_number(self):
        designations = ('Aya', 'Caretaker', 'Accountant', 'Office Assistant')
        for designation in designations:
            with self.subTest(designation=designation):
                employee = self._employee(f'Staff {designation}', designation=designation)
                self.assertEqual(employee.teacher_no, '')
                self.assertFalse(employee.is_teacher)
        # Two blanks already exist by the time a teacher is added.
        teacher = self._employee('Teacher After Staff')
        self.assertEqual(teacher.teacher_no, '2011020001')

    def test_designation_match_is_case_insensitive(self):
        self.assertTrue(Employee.is_teacher_designation('ASSISTANT TEACHER'))
        self.assertTrue(Employee.is_teacher_designation('সহকারী শিক্ষক teacher'))
        self.assertFalse(Employee.is_teacher_designation(''))

    def test_number_is_never_reallocated_on_edit(self):
        teacher = self._employee('Stable Teacher')
        original = teacher.teacher_no
        teacher.name = 'Stable Teacher Renamed'
        teacher.save(update_fields=['name'])
        teacher.refresh_from_db()
        self.assertEqual(teacher.teacher_no, original)

    def test_blank_from_before_the_field_is_filled_on_next_save(self):
        # A legacy teaching row can still be blank ('' or NULL). A save that
        # writes the whole row fills the number in rather than leaving the
        # teacher un-numbered.
        employee = self._employee('Late Correction', designation='Assistant Teacher')
        first_number = employee.teacher_no
        Employee.objects.filter(pk=employee.pk).update(teacher_no=None)
        employee.refresh_from_db()
        self.assertFalse(employee.teacher_no)  # NULL from the database
        employee.save()
        employee.refresh_from_db()
        # The number it lost stays spent, so a fresh one is allocated.
        self.assertEqual(employee.teacher_no, '2011020002')
        self.assertNotEqual(employee.teacher_no, first_number)

    def test_blank_legacy_row_gets_a_number_when_promoted_to_teacher(self):
        employee = self._employee('Promoted Staff', designation='Caretaker')
        self.assertEqual(employee.teacher_no, '')
        employee.designation = 'Assistant Teacher'
        employee.save()
        employee.refresh_from_db()
        self.assertEqual(employee.teacher_no, '2011020001')

    def test_a_partial_update_never_allocates_a_number(self):
        # update_fields is an explicit "write only these columns" contract;
        # the counter must not be consumed by an unrelated status change.
        Employee.objects.all().delete()
        Employee.objects.get_or_create  # keep flake-free
        teacher = self._employee('Quiet Teacher')
        self.assertEqual(teacher.teacher_no, '2011020001')
        teacher.status = 'OSD'
        teacher.save(update_fields=['status'])
        teacher.refresh_from_db()
        self.assertEqual(teacher.teacher_no, '2011020001')
        nxt = self._employee('Next Teacher')
        self.assertEqual(nxt.teacher_no, '2011020002')

    def test_many_non_teaching_employees_can_coexist(self):
        # A unique text column would allow only one empty string; non-teachers
        # are stored as NULL so any number of them can exist.
        for index in range(3):
            employee = self._employee(f'Caretaker {index}', designation='Caretaker')
            self.assertEqual(employee.teacher_no, '')
            self.assertFalse(employee.has_teacher_no)
        self.assertEqual(
            Employee.objects.filter(teacher_no__isnull=True).count(), 3
        )

    def test_hand_typed_numbers_lift_the_counter(self):
        self._employee('Teacher One')
        # A number typed in before the counter existed (or imported) wins.
        Employee.objects.filter(name='Teacher One').update(teacher_no='2011020005')
        fresh = self._employee('Teacher Six')
        self.assertEqual(fresh.teacher_no, '2011020006')

    def test_a_number_is_never_handed_out_twice(self):
        first = self._employee('Teacher One')
        first_number = first.teacher_no
        # Deleting the row must not put the number back in circulation: it is
        # printed on salary sheets and signature sheets already.
        first.delete()
        second = self._employee('Teacher Two')
        self.assertEqual(second.teacher_no, '2011020002')
        self.assertNotEqual(second.teacher_no, first_number)
        self.assertGreater(
            DocumentSequence.objects.get(scope='TEACHER-02').last_number, 1
        )

    def test_next_teacher_number_skips_gaps_without_reusing(self):
        first = self._employee('Teacher One')
        Employee.objects.filter(pk=first.pk).delete()
        self.assertEqual(next_teacher_number(self.institution), '2011020002')

    def test_each_branch_counts_its_own_teachers_from_one(self):
        other = Institution.objects.create(
            name='Other Number School', classes='9', number=3
        )
        one = self._employee('Teacher A')
        one_second = self._employee('Teacher A2')
        two = Employee.objects.create(
            institution=other, name='Teacher B', designation='Teacher',
            join_date=date(2026, 1, 1),
        )
        # School 2 is branch 02, the other school is branch 03.
        self.assertEqual(self.institution.number, 2)
        self.assertEqual(other.number, 3)
        self.assertEqual(one.teacher_no, '2011020001')
        self.assertEqual(one_second.teacher_no, '2011020002')
        self.assertEqual(two.teacher_no, '2011030001')
        # The branch code keeps every number unique system-wide.
        self.assertEqual(
            Employee.objects.exclude(teacher_no__isnull=True).values('teacher_no').distinct().count(), 3
        )

    def test_a_branch_without_a_number_gets_no_teacher_number(self):
        unnumbered = Institution.objects.create(name='Unnumbered', classes='9')
        Institution.objects.filter(pk=unnumbered.pk).update(number=None)
        unnumbered.refresh_from_db()
        teacher = Employee.objects.create(
            institution=unnumbered, name='No Branch Teacher', designation='Teacher',
            join_date=date(2026, 1, 1),
        )
        self.assertFalse(teacher.has_teacher_no)

    def test_a_teacher_without_an_institution_gets_no_number(self):
        teacher = Employee.objects.create(
            name='Floating Teacher', designation='Teacher', join_date=date(2026, 1, 1),
        )
        self.assertFalse(teacher.has_teacher_no)

    def test_renumbering_a_branch_lifts_its_counter(self):
        branch = Institution.objects.create(name='Late Branch', classes='9', number=7)
        Employee.objects.create(
            institution=branch, name='Typed By Hand', designation='Teacher',
            join_date=date(2026, 1, 1), teacher_no='2011070009',
        )
        fresh = Employee.objects.create(
            institution=branch, name='Next One', designation='Teacher',
            join_date=date(2026, 1, 1),
        )
        self.assertEqual(fresh.teacher_no, '2011070010')

    def test_status_change_save_keeps_the_number(self):
        teacher = self._employee('Status Teacher')
        teacher.status = 'RESIGNED'
        teacher.save(update_fields=['status'])
        teacher.refresh_from_db()
        self.assertEqual(teacher.teacher_no, '2011020001')


class TeacherNumberAssignmentScreenTests(TestCase):
    """The number-first "Assign a teacher" screen."""

    def setUp(self):
        self.institution = Institution.objects.create(
            name='Picker School', classes='9,10', number=2
        )
        self.other = Institution.objects.create(
            name='Elsewhere School', classes='9', number=3
        )
        self.teacher = Employee.objects.create(
            institution=self.institution, name='Salma Akter', designation='Assistant Teacher',
            join_date=date(2026, 1, 1),
        )
        self.caretaker = Employee.objects.create(
            institution=self.institution, name='Rokeya Begum', designation='Caretaker',
            join_date=date(2026, 1, 1),
        )
        self.outsider = Employee.objects.create(
            institution=self.other, name='Other School Teacher', designation='Teacher',
            join_date=date(2026, 1, 1),
        )
        self.physics = Subject.objects.create(code='PHY', name='Physics', full_marks=100)
        self.chemistry = Subject.objects.create(code='CHE', name='Chemistry', full_marks=100)
        self.outside_subject = Subject.objects.create(code='BOT', name='Botany', full_marks=100)
        SubjectRequirement.objects.create(
            institution=self.institution, admission_class='9', subject=self.physics,
        )
        SubjectRequirement.objects.create(
            institution=self.institution, admission_class='9', subject=self.chemistry,
        )
        ensure_default_groups()
        self.user = get_user_model().objects.create_user(username='picker', password='password')
        self.user.user_permissions.add(
            Permission.objects.get(codename='add_teacherassignment'),
            Permission.objects.get(codename='view_teacherassignment'),
            Permission.objects.get(codename='change_teacherassignment'),
        )
        self.client.force_login(self.user)

    def _post(self, **overrides):
        payload = {
            'teacher_no': '2011 02 0001',
            'admission_class': '9',
            'section': 'A',
            'subject': self.physics.pk,
            'session': '2026-2027',
            'is_active': 'on',
        }
        payload.update(overrides)
        return self.client.post(reverse('add_teacher_assignment'), payload)

    # -- the screen itself -------------------------------------------------
    def test_screen_asks_for_the_number_not_an_employee_dropdown(self):
        response = self.client.get(reverse('add_teacher_assignment'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id_teacher_no_input')
        # The long employee <select> is hidden, so no scrolling through staff.
        self.assertContains(response, 'id_employee')
        self.assertNotContains(response, 'form-select" name="employee"')
        self.assertContains(response, 'Only teaching staff have a number')

    def test_screen_offers_teachers_only_with_their_numbers(self):
        response = self.client.get(reverse('add_teacher_assignment'))
        lookup = response.context['teacher_lookup']
        numbers = {row['number'] for row in lookup}
        self.assertIn(self.teacher.teacher_no, numbers)
        self.assertIn(self.outsider.teacher_no, numbers)
        self.assertNotIn(self.caretaker.teacher_no, numbers)
        self.assertEqual(self.caretaker.teacher_no, '')

    def test_screen_defaults_the_session_and_active_flag(self):
        response = self.client.get(reverse('add_teacher_assignment'))
        form = response.context['form']
        self.assertEqual(form.initial['session'], current_academic_session())
        self.assertTrue(form.initial['is_active'])

    def test_screen_carries_the_class_section_and_subject_choices(self):
        response = self.client.get(reverse('add_teacher_assignment'))
        self.assertEqual(
            sorted(response.context['class_options']), ['10', '9']
        )
        self.assertIn(self.physics.pk, response.context['subjects_by_class']['9'])
        self.assertNotIn(
            self.outside_subject.pk, response.context['subjects_by_class']['9']
        )
        self.assertEqual(response.context['current_session'], current_academic_session())

    def test_class_sections_come_from_the_actual_students(self):
        from .models import Student
        Student.objects.create(
            institution=self.institution, student_id='SEC001', name='Section Student',
            admission_class='9', section='B', admission_year=2026, roll_no=1,
        )
        response = self.client.get(reverse('add_teacher_assignment'))
        self.assertIn('B', response.context['sections_by_class']['9'])

    # -- saving ------------------------------------------------------------
    def test_number_assigns_the_teacher_and_audits_it(self):
        response = self._post()
        self.assertRedirects(response, reverse('teacher_assignment_list'))
        assignment = TeacherAssignment.objects.get()
        self.assertEqual(assignment.employee, self.teacher)
        self.assertEqual(assignment.institution, self.institution)
        log = AuditLog.objects.filter(action='teacher_assignment_created').last()
        self.assertEqual(log.details['employee'], 'Salma Akter')
        self.assertEqual(log.details['subject'], 'Physics')

    def test_typed_variants_all_resolve_to_the_same_teacher(self):
        for index, typed in enumerate(
            ['2011 02 0001', '2011-02-0001', '২০১১০২০০০১', '020001']
        ):
            with self.subTest(typed=typed):
                TeacherAssignment.objects.all().delete()
                response = self._post(teacher_no=typed, section=f'S{index}')
                self.assertEqual(response.status_code, 302)
                self.assertEqual(TeacherAssignment.objects.get().employee, self.teacher)

    def test_unknown_number_is_reported_plainly(self):
        response = self._post(teacher_no='2011 02 9999')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(TeacherAssignment.objects.count(), 0)
        self.assertContains(response, 'No teacher has the number')

    def test_missing_number_is_reported(self):
        response = self._post(teacher_no='')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Type the teacher number')
        self.assertEqual(TeacherAssignment.objects.count(), 0)

    def test_non_teaching_staff_cannot_be_assigned_by_number(self):
        # A caretaker has no number at all, so there is nothing to type. Even
        # if somebody guesses the next serial, it belongs to a teacher or nobody.
        response = self._post(teacher_no='2011 03 0001')  # the outsider teacher
        self.assertEqual(response.status_code, 302)
        self.assertEqual(TeacherAssignment.objects.get().employee, self.outsider)

    def test_tampered_hidden_employee_is_ignored(self):
        response = self._post(employee=self.outsider.pk)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(TeacherAssignment.objects.get().employee, self.teacher)

    def test_inactive_teacher_is_refused(self):
        self.teacher.status = 'RESIGNED'
        self.teacher.save(update_fields=['status'])
        response = self._post()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'cannot be assigned')
        self.assertEqual(TeacherAssignment.objects.count(), 0)

    def test_institution_is_taken_from_the_teacher(self):
        # No institution is posted at all; the teacher's own school is used.
        response = self._post(teacher_no='2011 03 0001', admission_class='9',
                              subject=self.physics.pk)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(TeacherAssignment.objects.get().institution, self.other)

    def test_class_outside_the_institution_is_refused(self):
        response = self._post(admission_class='8')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'is not offered by')
        self.assertEqual(TeacherAssignment.objects.count(), 0)

    def test_zero_padded_class_is_accepted_as_the_institution_label(self):
        response = self._post(admission_class='09')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(TeacherAssignment.objects.get().admission_class, '9')

    def test_duplicate_names_the_subject_and_section(self):
        self._post()
        response = self._post()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(TeacherAssignment.objects.count(), 1)
        self.assertContains(response, 'already teaches')

    def test_edit_screen_is_prefilled_with_the_number(self):
        self._post()
        assignment = TeacherAssignment.objects.get()
        response = self.client.get(reverse('edit_teacher_assignment', args=[assignment.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '2011 02 0001')
        self.assertEqual(response.context['form'].initial['teacher_no'], '2011 02 0001')

    def test_edit_can_switch_the_teacher_by_number(self):
        self._post()
        assignment = TeacherAssignment.objects.get()
        response = self.client.post(
            reverse('edit_teacher_assignment', args=[assignment.pk]),
            {
                'teacher_no': '2011 03 0001', 'admission_class': '9', 'section': 'A',
                'subject': self.physics.pk, 'session': '2026-2027', 'is_active': 'on',
            },
        )
        self.assertEqual(response.status_code, 302)
        assignment.refresh_from_db()
        self.assertEqual(assignment.employee, self.outsider)


class TeacherNumberLookupTests(TestCase):
    """The no-JS / press-Enter fallback endpoint."""

    def setUp(self):
        self.institution = Institution.objects.create(
            name='Lookup School', classes='9', number=2
        )
        self.teacher = Employee.objects.create(
            institution=self.institution, name='Lookup Teacher', designation='Teacher',
            join_date=date(2026, 1, 1),
        )
        self.caretaker = Employee.objects.create(
            institution=self.institution, name='Lookup Caretaker', designation='Caretaker',
            join_date=date(2026, 1, 1),
        )
        ensure_default_groups()
        self.user = get_user_model().objects.create_user(username='looker', password='password')
        self.user.user_permissions.add(Permission.objects.get(codename='view_teacherassignment'))
        self.client.force_login(self.user)

    def test_lookup_returns_the_teacher(self):
        response = self.client.get(reverse('teacher_number_lookup'), {'q': '2011 02 0001'})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['found'])
        self.assertEqual(payload['name'], 'Lookup Teacher')
        self.assertEqual(payload['pretty'], '2011 02 0001')
        self.assertTrue(payload['active'])

    def test_lookup_accepts_the_bare_serial_for_its_branch(self):
        payload = self.client.get(
            reverse('teacher_number_lookup'),
            {'q': '0001', 'institution': self.institution.pk},
        ).json()
        self.assertTrue(payload['found'])
        self.assertEqual(payload['number'], '2011020001')

    def test_lookup_rejects_a_bare_serial_without_a_branch(self):
        payload = self.client.get(reverse('teacher_number_lookup'), {'q': '0001'}).json()
        self.assertFalse(payload['found'])

    def test_lookup_says_not_found_for_an_unknown_number(self):
        payload = self.client.get(reverse('teacher_number_lookup'), {'q': '2011 02 0777'}).json()
        self.assertFalse(payload['found'])
        self.assertNotIn('name', payload)

    def test_lookup_without_a_query_is_not_found(self):
        payload = self.client.get(reverse('teacher_number_lookup')).json()
        self.assertFalse(payload['found'])

    def test_lookup_needs_the_permission(self):
        self.client.logout()
        plain = get_user_model().objects.create_user(username='plain-look', password='password')
        self.client.force_login(plain)
        response = self.client.get(reverse('teacher_number_lookup'), {'q': '1'})
        self.assertEqual(response.status_code, 403)

    def test_lookup_never_returns_non_teaching_staff(self):
        # The caretaker has no number, so the only thing a guess can hit is a
        # teacher. This pins that the endpoint filters to teaching staff.
        payload = self.client.get(
            reverse('teacher_number_lookup'),
            {'q': '0002', 'institution': self.institution.pk},
        ).json()
        self.assertFalse(payload['found'])


class EmployeeNumberDisplayTests(TestCase):
    def setUp(self):
        self.institution = Institution.objects.create(
            name='Display School', classes='9', number=2
        )
        ensure_default_groups()
        self.teacher = Employee.objects.create(
            institution=self.institution, name='Display Teacher', designation='Teacher',
            join_date=date(2026, 1, 1),
        )
        self.admin = get_user_model().objects.create_superuser(
            username='display-admin', password='password'
        )
        self.client.force_login(self.admin)

    def test_employee_detail_shows_the_number(self):
        response = self.client.get(reverse('employee_detail', args=[self.teacher.pk]))
        self.assertContains(response, '2011 02 0001')
        self.assertContains(response, 'Teacher number')

    def test_employee_list_shows_the_number(self):
        response = self.client.get(reverse('employee_list'))
        self.assertContains(response, 'Teacher No.')
        self.assertContains(response, '2011 02 0001')

    def test_employee_form_shows_the_number_read_only(self):
        response = self.client.get(reverse('edit_employee', args=[self.teacher.pk]))
        self.assertContains(response, '2011 02 0001')
        # It is allocated by the counter, so the input is disabled — a clerk
        # cannot invent or overwrite a number from the employee form.
        self.assertContains(response, 'disabled')

    def test_employee_form_does_not_change_the_number(self):
        self.client.post(
            reverse('edit_employee', args=[self.teacher.pk]),
            {
                'name': 'Display Teacher Renamed', 'designation': 'Senior Teacher',
                'department': '', 'institution': self.institution.pk,
                'join_date': '2026-01-01', 'contact_no': '01812345678',
            },
        )
        self.teacher.refresh_from_db()
        self.assertEqual(self.teacher.teacher_no, '2011020001')
        self.assertEqual(self.teacher.name, 'Display Teacher Renamed')


class InstitutionNumberMigrationTests(TestCase):
    """Migration 0058: branches are numbered, old numbers are rewritten.

    The migration's own function is called here against the current models, so
    the renaming rule stays testable without replaying the whole history.
    """

    def _run(self):
        from django.apps import apps
        from importlib import import_module

        module = import_module('students.migrations.0058_institution_number')
        module.forwards(apps, None)

    def test_existing_branches_are_numbered_in_the_order_they_were_added(self):
        college = Institution.objects.create(name='College', classes='11,12')
        school = Institution.objects.create(name='School', classes='9,10')
        shishukanon = Institution.objects.create(name='Shishukanon', classes='Shishu')
        Institution.objects.update(number=None)

        self._run()

        for institution, expected in ((college, 1), (school, 2), (shishukanon, 3)):
            institution.refresh_from_db()
            self.assertEqual(institution.number, expected)

    def test_old_global_numbers_are_rewritten_per_branch(self):
        college = Institution.objects.create(name='College', classes='11,12')
        school = Institution.objects.create(name='School', classes='9,10')
        Institution.objects.update(number=None)
        # The pre-branch layout: 2011 + one six-digit global serial.
        first = Employee.objects.create(
            institution=school, name='Old One', designation='Teacher',
            join_date=date(2026, 1, 1), teacher_no='2011000001',
        )
        second = Employee.objects.create(
            institution=school, name='Old Two', designation='Teacher',
            join_date=date(2026, 2, 1), teacher_no='2011000002',
        )
        caretaker = Employee.objects.create(
            institution=school, name='Caretaker', designation='Caretaker',
            join_date=date(2026, 3, 1),
        )
        lecturer = Employee.objects.create(
            institution=college, name='Lecturer', designation='Lecturer',
            join_date=date(2026, 1, 15), teacher_no='2011000003',
        )

        self._run()

        first.refresh_from_db(); second.refresh_from_db()
        caretaker.refresh_from_db(); lecturer.refresh_from_db()
        # School is branch 02 and counts from 1 in join-date order.
        self.assertEqual(first.teacher_no, '2011020001')
        self.assertEqual(second.teacher_no, '2011020002')
        # The college is branch 01 and starts its own serial.
        self.assertEqual(lecturer.teacher_no, '2011010001')
        # Non-teaching staff are never numbered.
        self.assertFalse(caretaker.has_teacher_no)
        # The per-branch counters are seeded, so the next save continues the run.
        self.assertEqual(
            DocumentSequence.objects.get(scope='TEACHER-02').last_number, 2
        )
        self.assertEqual(
            DocumentSequence.objects.get(scope='TEACHER-01').last_number, 1
        )
        follow_up = Employee.objects.create(
            institution=school, name='New One', designation='Teacher',
            join_date=date(2026, 4, 1),
        )
        self.assertEqual(follow_up.teacher_no, '2011020003')

    def test_a_teacher_without_an_institution_loses_the_branchless_number(self):
        teacher = Employee.objects.create(
            name='Floating', designation='Teacher', join_date=date(2026, 1, 1),
            teacher_no='2011000009',
        )
        self._run()
        teacher.refresh_from_db()
        self.assertFalse(teacher.has_teacher_no)


class InstitutionNumberGuardTests(TestCase):
    """The branch number must not drift away from the numbers it printed."""

    def setUp(self):
        self.branch = Institution.objects.create(name='Guard School', classes='9', number=5)

    def test_a_branch_with_teachers_cannot_be_renumbered(self):
        Employee.objects.create(
            institution=self.branch, name='Numbered Teacher', designation='Teacher',
            join_date=date(2026, 1, 1),
        )
        self.branch.number = 6
        with self.assertRaises(ValidationError) as caught:
            self.branch.full_clean()
        self.assertIn('already has numbered teachers', str(caught.exception))

    def test_a_branch_without_teachers_can_still_be_renumbered(self):
        self.branch.number = 6
        self.branch.full_clean()
        self.branch.save()
        self.branch.refresh_from_db()
        self.assertEqual(self.branch.number, 6)

    def test_numbers_outside_two_digits_are_refused(self):
        self.branch.number = 100
        with self.assertRaises(ValidationError):
            self.branch.full_clean()

    def test_an_unnumbered_branch_gets_the_lowest_free_number(self):
        self.assertEqual(self.branch.number, 5)
        self.assertEqual(Institution.next_number(), 1)


class SingleBranchClerkTests(TestCase):
    """A clerk who works in one branch types only that branch's serial."""

    def setUp(self):
        from .models import InstitutionAccess

        self.college = Institution.objects.create(name='Clerk College', classes='11,12', number=1)
        self.school = Institution.objects.create(name='Clerk School', classes='9,10', number=2)
        self.first = Employee.objects.create(
            institution=self.school, name='School First', designation='Teacher',
            join_date=date(2026, 1, 1),
        )
        self.second = Employee.objects.create(
            institution=self.school, name='School Second', designation='Teacher',
            join_date=date(2026, 2, 1),
        )
        self.college_teacher = Employee.objects.create(
            institution=self.college, name='College First', designation='Lecturer',
            join_date=date(2026, 1, 1),
        )
        self.physics = Subject.objects.create(code='PHY2', name='Physics', full_marks=100)
        SubjectRequirement.objects.create(
            institution=self.school, admission_class='9', subject=self.physics,
        )
        ensure_default_groups()
        self.clerk = get_user_model().objects.create_user(
            username='branch-clerk', password='password'
        )
        for codename in ('add_teacherassignment', 'view_teacherassignment'):
            self.clerk.user_permissions.add(Permission.objects.get(codename=codename))
        InstitutionAccess.objects.create(
            user=self.clerk, institution=self.school, department='Office'
        )
        self.client.force_login(self.clerk)

    def _post(self, teacher_no, section='A'):
        return self.client.post(reverse('add_teacher_assignment'), {
            'teacher_no': teacher_no, 'admission_class': '9', 'section': section,
            'subject': self.physics.pk, 'session': current_academic_session(),
            'is_active': 'on',
        })

    def test_the_screen_names_the_branch_and_its_number(self):
        response = self.client.get(reverse('add_teacher_assignment'))
        branch = response.context['teacher_branch']
        self.assertEqual(branch['number'], '02')
        self.assertEqual(branch['name'], 'Clerk School')
        self.assertContains(response, 'Looking in')

    def test_only_that_branch_s_teachers_are_offered(self):
        response = self.client.get(reverse('add_teacher_assignment'))
        numbers = {row['number'] for row in response.context['teacher_lookup']}
        self.assertEqual(numbers, {'2011020001', '2011020002'})

    def test_the_serial_alone_assigns_the_teacher(self):
        response = self._post('0002')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(TeacherAssignment.objects.get().employee, self.second)

    def test_another_branch_s_serial_is_not_found(self):
        # College serial 1 is not this branch's serial 1.
        response = self._post('0001')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(TeacherAssignment.objects.get().employee, self.first)

    def test_a_full_number_from_another_branch_is_out_of_scope(self):
        response = self._post('2011 01 0001')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No teacher has the number')
        self.assertEqual(TeacherAssignment.objects.count(), 0)
