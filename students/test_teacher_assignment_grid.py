"""The class-at-a-time teacher assignment grid.

The registry form asks about one teacher/class/section/subject row at a time.
The office asked for the opposite shape: pick class + section, see every
subject of the curriculum as a row, and search the teacher beside each row —
because one teacher usually takes several subjects and several classes.

Covers: the screen's layout + narrowing, one-row-per-subject, the teacher
search resolution (number, serial, name) on POST, replacing/clearing a row,
section scoping, permissions, institution scoping, and the audit trail.
"""
from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from .models import (
    AuditLog, Employee, Institution, InstitutionAccess, SectionCapacity,
    Student, Subject, SubjectRequirement, TeacherAssignment,
)
from .permissions import ensure_default_groups


class TeacherAssignmentGridTests(TestCase):
    def setUp(self):
        self.institution = Institution.objects.create(name='Grid School', classes='9,10')
        self.other = Institution.objects.create(name='Other Grid School', classes='9,10')
        self.physics = Subject.objects.create(code='PHY', name='Physics', full_marks=100)
        self.chemistry = Subject.objects.create(code='CHE', name='Chemistry', full_marks=100)
        self.maths = Subject.objects.create(code='MAT', name='Mathematics', full_marks=100)
        self.outside = Subject.objects.create(code='BOT', name='Botany', full_marks=100)
        for subject in (self.physics, self.chemistry, self.maths):
            SubjectRequirement.objects.create(
                institution=self.institution, admission_class='9', subject=subject,
            )
        SubjectRequirement.objects.create(
            institution=self.institution, admission_class='10', subject=self.physics,
        )
        self.salma = Employee.objects.create(
            institution=self.institution, name='Salma Akter',
            designation='Assistant Teacher', join_date=date(2026, 1, 1),
        )
        self.karim = Employee.objects.create(
            institution=self.institution, name='Karim Mia',
            designation='Senior Teacher', join_date=date(2026, 1, 1),
        )
        self.college_teacher = Employee.objects.create(
            institution=self.other, name='College Teacher',
            designation='Teacher', join_date=date(2026, 1, 1),
        )
        Student.objects.create(
            institution=self.institution, student_id='GS001', name='Grid Student',
            admission_class='9', section='A', admission_year=2026, roll_no=1,
        )
        Student.objects.create(
            institution=self.institution, student_id='GS002', name='Grid Student B',
            admission_class='9', section='B', admission_year=2026, roll_no=2,
        )
        SectionCapacity.objects.create(
            institution=self.institution, admission_class='9', section='C', capacity=40,
        )
        ensure_default_groups()
        self.user = get_user_model().objects.create_user(
            username='grid-clerk', password='password',
        )
        for codename in (
            'add_teacherassignment', 'change_teacherassignment',
            'view_teacherassignment',
        ):
            self.user.user_permissions.add(Permission.objects.get(codename=codename))
        self.client.force_login(self.user)

    def _get(self, **params):
        query = {'institution': self.institution.pk, 'admission_class': '9'}
        query.update(params)
        return self.client.get(reverse('teacher_assignment_grid'), query)

    def _post(self, rows, **params):
        payload = {
            'institution': self.institution.pk,
            'admission_class': '9',
            'section': 'A',
            'session': '2026-2027',
        }
        section = params.pop('section', 'A')
        payload['section'] = section
        for subject, value in rows.items():
            if isinstance(value, dict):
                payload[f'teacher_{subject.pk}'] = value.get('text', '')
                payload[f'employee_{subject.pk}'] = value.get('employee', '')
            else:
                payload[f'teacher_{subject.pk}'] = value
        return self.client.post(reverse('teacher_assignment_grid'), payload)

    # -- the screen -------------------------------------------------------

    def test_grid_lays_out_one_row_per_curriculum_subject(self):
        response = self._get()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [row['subject'].name for row in response.context['rows']],
            sorted(['Physics', 'Chemistry', 'Mathematics']),
        )
        for subject in (self.physics, self.chemistry, self.maths):
            self.assertContains(response, f'name="teacher_{subject.pk}"')
            self.assertContains(response, f'id="employee_{subject.pk}"')

    def test_sections_come_from_students_and_capacity(self):
        response = self._get()
        self.assertEqual(response.context['sections'], ['A', 'B', 'C'])

    def test_grid_shows_the_teacher_already_on_a_row(self):
        TeacherAssignment.objects.create(
            institution=self.institution, employee=self.salma,
            admission_class='9', section='A', subject=self.physics,
            session='2026-2027',
        )
        response = self._get(section='A')
        physics_row = next(
            row for row in response.context['rows'] if row['subject'] == self.physics
        )
        self.assertEqual(physics_row['current_employee'], self.salma.pk)
        self.assertContains(response, f'value="{self.salma.teacher_no_display}')

    def test_whole_class_rows_ignore_sectioned_assignments(self):
        TeacherAssignment.objects.create(
            institution=self.institution, employee=self.salma,
            admission_class='9', section='A', subject=self.physics,
            session='2026-2027',
        )
        response = self._get()  # no section = whole class
        physics_row = next(
            row for row in response.context['rows'] if row['subject'] == self.physics
        )
        self.assertIsNone(physics_row['current'])

    def test_a_class_outside_the_institution_is_a_404(self):
        response = self._get(admission_class='8')
        self.assertEqual(response.status_code, 404)

    # -- saving the grid --------------------------------------------------

    def test_one_save_writes_every_row(self):
        response = self._post({
            self.physics: self.salma.teacher_no,
            self.chemistry: self.salma.teacher_no,
            self.maths: self.karim.teacher_no,
        })
        self.assertEqual(response.status_code, 302)
        rows = TeacherAssignment.objects.filter(is_active=True).order_by('subject__name')
        self.assertEqual(
            [(row.subject.name, row.employee.name) for row in rows],
            [('Chemistry', 'Salma Akter'), ('Mathematics', 'Karim Mia'),
             ('Physics', 'Salma Akter')],
        )
        self.assertTrue(all(row.section == 'A' for row in rows))
        self.assertTrue(all(row.session == '2026-2027' for row in rows))
        self.assertEqual(
            AuditLog.objects.filter(action='teacher_assignment_created').count(), 3,
        )

    def test_the_same_teacher_can_take_several_subjects(self):
        self._post({self.physics: self.salma.teacher_no,
                    self.chemistry: self.salma.teacher_no})
        self.assertEqual(
            TeacherAssignment.objects.filter(employee=self.salma, is_active=True).count(),
            2,
        )

    def test_changing_a_row_retires_the_old_row_instead_of_deleting_it(self):
        self._post({self.physics: self.salma.teacher_no})
        self._post({self.physics: self.karim.teacher_no})
        physics = TeacherAssignment.objects.filter(subject=self.physics)
        self.assertEqual(physics.count(), 2)
        self.assertEqual(
            physics.filter(is_active=True).get().employee, self.karim,
        )
        self.assertEqual(
            physics.filter(is_active=False).get().employee, self.salma,
        )
        self.assertTrue(
            AuditLog.objects.filter(action='teacher_assignment_unassigned').exists()
        )

    def test_an_empty_row_removes_that_subject_teacher(self):
        self._post({self.physics: self.salma.teacher_no})
        self._post({self.physics: ''})
        self.assertFalse(
            TeacherAssignment.objects.filter(subject=self.physics, is_active=True).exists()
        )

    def test_a_name_and_a_serial_both_resolve(self):
        self._post({self.physics: '2011 02 0002'})
        self._post({self.maths: 'Karim Mia'})
        self.assertEqual(
            set(
                TeacherAssignment.objects.filter(is_active=True)
                .values_list('employee__name', flat=True)
            ),
            {'Karim Mia'},
        )

    def test_the_hidden_picked_employee_id_wins(self):
        # The JavaScript picker posts the id as well; that is the authority.
        response = self._post({
            self.physics: {'text': '2011 02 0001 · Salma Akter',
                           'employee': self.salma.pk},
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            TeacherAssignment.objects.get(subject=self.physics).employee, self.salma,
        )

    def test_an_inactive_teacher_is_refused_with_a_message(self):
        self.karim.status = 'RESIGNED'
        self.karim.save(update_fields=['status'])
        response = self._post({self.physics: self.karim.teacher_no})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(TeacherAssignment.objects.exists())
        self.assertContains(response, 'cannot be assigned')

    def test_a_teacher_of_another_institution_cannot_be_posted(self):
        response = self._post({self.physics: self.college_teacher.teacher_no})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(TeacherAssignment.objects.exists())
        self.assertContains(response, 'no teacher found')

    def test_a_bad_row_saves_nothing(self):
        response = self._post({
            self.physics: self.salma.teacher_no,
            self.chemistry: '2011 02 0099',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(TeacherAssignment.objects.exists())

    def test_an_assignment_only_subject_is_still_listed(self):
        # A subject removed from the curriculum after it was assigned must not
        # vanish from the grid, or the office could never clear it.
        TeacherAssignment.objects.create(
            institution=self.institution, employee=self.salma,
            admission_class='9', section='A', subject=self.outside,
            session='2026-2027',
        )
        response = self._get(section='A')
        names = [row['subject'].name for row in response.context['rows']]
        self.assertIn('Botany', names)
        outside_row = next(
            row for row in response.context['rows'] if row['subject'] == self.outside
        )
        self.assertFalse(outside_row['in_curriculum'])

    def test_the_other_classes_of_a_teacher_are_shown(self):
        TeacherAssignment.objects.create(
            institution=self.institution, employee=self.salma,
            admission_class='10', section='A', subject=self.physics,
            session='2026-2027',
        )
        response = self._get()
        salma = next(
            teacher for teacher in response.context['teacher_rows']
            if teacher['id'] == self.salma.pk
        )
        self.assertEqual(salma['also'], ['Class 10 (A) · Physics'])

    def test_a_teacher_without_a_number_still_renders_a_clean_label(self):
        unnumbered = Employee.objects.create(
            institution=self.institution, name='Visiting Lecturer',
            designation='Teacher', join_date=date(2026, 1, 1),
        )
        # A legacy teaching row from before the number column existed.
        Employee.objects.filter(pk=unnumbered.pk).update(teacher_no=None)
        unnumbered.refresh_from_db()
        TeacherAssignment.objects.create(
            institution=self.institution, employee=unnumbered,
            admission_class='9', section='A', subject=self.physics,
            session='2026-2027',
        )
        response = self._get(section='A')
        physics_row = next(
            row for row in response.context['rows'] if row['subject'] == self.physics
        )
        self.assertEqual(physics_row['current_label'], 'Visiting Lecturer')
        # And the no-JS text path still resolves that label to the same teacher.
        response = self._post({self.physics: 'Visiting Lecturer'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            TeacherAssignment.objects.filter(
                subject=self.physics, is_active=True,
            ).get().employee, unnumbered,
        )

    def test_the_grid_is_idempotent(self):
        self._post({self.physics: self.salma.teacher_no})
        response = self._post({self.physics: self.salma.teacher_no})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            TeacherAssignment.objects.filter(subject=self.physics).count(), 1,
        )

    # -- permissions and scoping -----------------------------------------

    def test_view_without_write_renders_a_read_only_grid(self):
        viewer = get_user_model().objects.create_user(
            username='grid-viewer', password='password',
        )
        viewer.user_permissions.add(
            Permission.objects.get(codename='view_teacherassignment')
        )
        self.client.force_login(viewer)
        response = self._get()
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['can_edit'])
        self.assertContains(response, 'readonly')
        post = self._post({self.physics: self.salma.teacher_no})
        self.assertEqual(post.status_code, 403)
        self.assertFalse(TeacherAssignment.objects.exists())

    def test_user_without_permission_is_forbidden(self):
        self.client.logout()
        plain = get_user_model().objects.create_user(
            username='grid-plain', password='password',
        )
        self.client.force_login(plain)
        self.assertEqual(
            self.client.get(reverse('teacher_assignment_grid')).status_code, 403,
        )

    def test_a_scoped_clerk_cannot_open_another_institution(self):
        # The clerk holds access to the *other* branch only. Asking for this
        # branch by id is refused by the resolver: the page falls back to the
        # clerk's own branch (and the form posts are scoped the same way).
        InstitutionAccess.objects.create(
            user=self.user, institution=self.other, department='Office', is_active=True,
        )
        response = self.client.get(reverse('teacher_assignment_grid'), {
            'institution': self.institution.pk, 'admission_class': '9',
        })
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(response.context['institution'], self.institution)
        self.assertEqual(response.context['institution'], self.other)
        # And no assignment in this branch can be created through the grid.
        post = self.client.post(reverse('teacher_assignment_grid'), {
            'institution': self.institution.pk, 'admission_class': '9',
            'section': 'A', 'session': '2026-2027',
            f'teacher_{self.physics.pk}': self.salma.teacher_no,
        })
        self.assertEqual(post.status_code, 200)
        self.assertFalse(TeacherAssignment.objects.exists())

    def test_grid_entries_are_scoped_to_the_institution(self):
        self._post({self.physics: self.salma.teacher_no})
        assignment = TeacherAssignment.objects.get()
        self.assertEqual(assignment.institution, self.institution)
        # The other branch's registry is untouched.
        self.assertFalse(
            TeacherAssignment.objects.filter(institution=self.other).exists()
        )
