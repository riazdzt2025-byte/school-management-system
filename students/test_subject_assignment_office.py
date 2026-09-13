"""Subject Assignment (বিষয় নির্ধারণ) as an Office department workflow.

Covers the reorganisation that moves Subject Assignment under the Office
department:

- The sidebar shows "Subject Assignments" inside the Office group for users
  holding students.view_subjectrequirement, and the old duplicate entry
  points on the Students/Admission list pages are gone.
- The Office group carries the SubjectRequirement list/add/edit/delete
  permissions the workflow needs (curriculum auto-fill reuses add).
- Exam/Accounts keep a read-only view so the existing "Go to Subject
  Assignments" links in the exam/marks workflow keep working, and the
  Subjects group keeps its subject-master permissions.
- A user without the read permission cannot use the workflow via GET/POST.
- An Office clerk scoped to Institution A cannot read or mutate
  Institution B's assignments.
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import reverse

from .models import Institution, InstitutionAccess, Subject, SubjectRequirement
from .permissions import ensure_default_groups, sync_user_department_permissions


def sr_permission(action):
    return Permission.objects.get(
        content_type=ContentType.objects.get_for_model(SubjectRequirement),
        codename=f'{action}_subjectrequirement',
    )


def grant_sr(user, *actions):
    for action in actions:
        user.user_permissions.add(sr_permission(action))


class OfficeGroupPermissionTests(TestCase):
    """The default department groups line up with the new Office workflow."""

    def setUp(self):
        ensure_default_groups()
        self.office = Group.objects.get(name='Office')
        self.exam = Group.objects.get(name='Exam')
        self.accounts = Group.objects.get(name='Accounts')
        self.subjects = Group.objects.get(name='Subjects')

    def _codenames(self, group, model):
        ct = ContentType.objects.get_for_model(model)
        return set(group.permissions.filter(content_type=ct).values_list('codename', flat=True))

    def test_office_group_has_full_assignment_access(self):
        perms = self._codenames(self.office, SubjectRequirement)
        self.assertEqual(
            perms,
            {'view_subjectrequirement', 'add_subjectrequirement',
             'change_subjectrequirement', 'delete_subjectrequirement'},
        )

    def test_office_group_keeps_existing_permissions(self):
        from .models import Student
        perms = self._codenames(self.office, Student)
        self.assertEqual(perms, {'add_student', 'change_student', 'delete_student', 'view_student'})

    def test_exam_group_gets_read_only_assignment_view(self):
        perms = self._codenames(self.exam, SubjectRequirement)
        self.assertEqual(perms, {'view_subjectrequirement'})
        # Exam keeps its marks-entry permissions untouched.
        from .models import ExamMark
        self.assertEqual(
            self._codenames(self.exam, ExamMark),
            {'add_exammark', 'change_exammark', 'delete_exammark'},
        )

    def test_accounts_group_gets_read_only_assignment_view(self):
        self.assertEqual(
            self._codenames(self.accounts, SubjectRequirement),
            {'view_subjectrequirement'},
        )

    def test_subjects_group_keeps_subject_master_permissions(self):
        from .models import Subject
        self.assertEqual(
            self._codenames(self.subjects, Subject),
            {'add_subject', 'change_subject', 'delete_subject'},
        )
        # Read access to the assignment list (it used to be login-only).
        self.assertEqual(
            self._codenames(self.subjects, SubjectRequirement),
            {'view_subjectrequirement'},
        )

    def test_office_department_user_syncs_into_office_group(self):
        user = get_user_model().objects.create_user(username='office-user', password='password')
        institution = Institution.objects.create(name='Sync School', classes='6,9')
        InstitutionAccess.objects.create(
            user=user, institution=institution, department='Office',
        )
        sync_user_department_permissions(user)
        user = get_user_model().objects.get(pk=user.pk)  # fresh perm cache
        self.assertIn(self.office, user.groups.all())
        for codename in ('view_subjectrequirement', 'add_subjectrequirement',
                         'change_subjectrequirement', 'delete_subjectrequirement'):
            self.assertTrue(user.has_perm(f'students.{codename}'), codename)


class SubjectAssignmentNavigationTests(TestCase):
    """The Office sidebar subtab replaces the old duplicate entry points."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(username='nav-user', password='password')
        self.list_url = reverse('subject_requirement_list')

    def test_office_subtab_shown_to_authorised_user(self):
        grant_sr(self.user, 'view')
        self.client.force_login(self.user)
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn(f'href="{self.list_url}"', body)
        self.assertIn('Subject Assignments', body)

    def test_office_subtab_hidden_from_unauthorised_user(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(f'href="{self.list_url}"', response.content.decode())

    def test_old_duplicate_entries_removed_from_student_list(self):
        admin = get_user_model().objects.create_superuser(
            username='nav-admin', password='password', email='nav@example.com',
        )
        self.client.force_login(admin)
        response = self.client.get(reverse('student_list'))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        # Old page-header button and the old tab-row entry are gone…
        self.assertNotIn('📚 Subject Assignments', body)
        self.assertNotIn('btn-sm btn-outline-secondary">Subject Assignments', body)
        # …but the Office sidebar subtab is there (admin has the read perm).
        self.assertIn(f'href="{self.list_url}"', body)

    def test_old_duplicate_entry_removed_from_admission_list(self):
        admin = get_user_model().objects.create_superuser(
            username='adm-nav-admin', password='password', email='adm-nav@example.com',
        )
        self.client.force_login(admin)
        response = self.client.get(reverse('admission_application_list'))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertNotIn('btn-sm btn-outline-secondary">Subject Assignments', body)


class SubjectAssignmentAccessControlTests(TestCase):
    """GET/POST access to the workflow, role by role."""

    def setUp(self):
        self.institution = Institution.objects.create(name='Access School', classes='6,9')
        self.subject = Subject.objects.create(code='ACC', name='Access Subject', full_marks=100)
        self.requirement = SubjectRequirement.objects.create(
            institution=self.institution, admission_class='9', group='SCI',
            subject=self.subject, requirement_type='MANDATORY',
        )

        self.unauthorised = get_user_model().objects.create_user(username='no-perm', password='password')
        InstitutionAccess.objects.create(
            user=self.unauthorised, institution=self.institution, department='Office',
        )
        self.viewer = get_user_model().objects.create_user(username='viewer', password='password')
        grant_sr(self.viewer, 'view')
        InstitutionAccess.objects.create(
            user=self.viewer, institution=self.institution, department='Exam',
        )
        self.office = get_user_model().objects.create_user(username='office-op', password='password')
        grant_sr(self.office, 'view', 'add', 'change', 'delete')
        InstitutionAccess.objects.create(
            user=self.office, institution=self.institution, department='Office',
        )

    def login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session['selected_institution_id'] = str(self.institution.pk)
        session['selected_department'] = 'Office'
        session.save()

    def test_unauthorised_user_cannot_open_list_via_get(self):
        self.login(self.unauthorised)
        response = self.client.get(reverse('subject_requirement_list'))
        self.assertEqual(response.status_code, 403)

    def test_unauthorised_user_cannot_add_via_post(self):
        self.login(self.unauthorised)
        response = self.client.post(reverse('add_subject_requirement'), {
            'institution': self.institution.pk, 'admission_class': '9', 'group': '',
            'subject': self.subject.pk, 'requirement_type': 'MANDATORY',
        })
        self.assertEqual(response.status_code, 403)
        self.assertEqual(SubjectRequirement.objects.count(), 1)

    def test_unauthorised_user_cannot_edit_delete_autofill(self):
        self.login(self.unauthorised)
        self.assertEqual(
            self.client.get(reverse('edit_subject_requirement', args=[self.requirement.pk])).status_code, 403)
        self.assertEqual(
            self.client.get(reverse('delete_subject_requirement', args=[self.requirement.pk])).status_code, 403)
        response = self.client.post(
            reverse('quick_update_requirement_type', args=[self.requirement.pk]),
            {'requirement_type': 'OPTIONAL'},
        )
        self.assertEqual(response.status_code, 403)
        response = self.client.post(reverse('auto_populate_subject_requirements'), {
            'institution': self.institution.pk, 'admission_class': '9', 'group': '',
        })
        self.assertEqual(response.status_code, 403)

    def test_view_only_user_can_list_but_not_write(self):
        self.login(self.viewer)
        self.assertEqual(self.client.get(reverse('subject_requirement_list')).status_code, 200)
        self.assertEqual(self.client.get(reverse('add_subject_requirement')).status_code, 403)
        self.assertEqual(
            self.client.get(reverse('edit_subject_requirement', args=[self.requirement.pk])).status_code, 403)
        self.assertEqual(
            self.client.get(reverse('delete_subject_requirement', args=[self.requirement.pk])).status_code, 403)
        response = self.client.post(reverse('auto_populate_subject_requirements'), {
            'institution': self.institution.pk, 'admission_class': '9', 'group': '',
        })
        self.assertEqual(response.status_code, 403)

    def test_office_user_can_open_all_workflow_urls(self):
        self.login(self.office)
        self.assertEqual(self.client.get(reverse('subject_requirement_list')).status_code, 200)
        self.assertEqual(self.client.get(reverse('add_subject_requirement')).status_code, 200)
        self.assertEqual(
            self.client.get(reverse('edit_subject_requirement', args=[self.requirement.pk])).status_code, 200)
        self.assertEqual(
            self.client.get(reverse('delete_subject_requirement', args=[self.requirement.pk])).status_code, 200)

    def test_office_user_can_add_assignment(self):
        self.login(self.office)
        other = Subject.objects.create(code='ACB', name='Access B', full_marks=100)
        response = self.client.post(reverse('add_subject_requirement'), {
            'institution': self.institution.pk, 'admission_class': '9', 'group': 'SCI',
            'subject': other.pk, 'requirement_type': 'OPTIONAL',
            'optional_set_key': 'set-a',
        })
        self.assertRedirects(response, reverse('subject_requirement_list'))
        self.assertTrue(SubjectRequirement.objects.filter(
            institution=self.institution, admission_class='9', subject=other,
            requirement_type='OPTIONAL',
        ).exists())

    def test_office_user_can_edit_assignment(self):
        self.login(self.office)
        response = self.client.post(
            reverse('edit_subject_requirement', args=[self.requirement.pk]),
            {
                'institution': self.institution.pk, 'admission_class': '9', 'group': 'SCI',
                'subject': self.subject.pk, 'requirement_type': 'CONDITIONAL',
                'condition_religion': 'Islam',
            },
        )
        self.assertRedirects(response, reverse('subject_requirement_list'))
        self.requirement.refresh_from_db()
        self.assertEqual(self.requirement.requirement_type, 'CONDITIONAL')
        self.assertEqual(self.requirement.condition_religion, 'Islam')

    def test_office_user_can_quick_update_type(self):
        self.login(self.office)
        response = self.client.post(
            reverse('quick_update_requirement_type', args=[self.requirement.pk]),
            {'requirement_type': 'OPTIONAL'},
        )
        self.assertRedirects(response, reverse('subject_requirement_list'))
        self.requirement.refresh_from_db()
        self.assertEqual(self.requirement.requirement_type, 'OPTIONAL')

    def test_office_user_can_delete_assignment(self):
        self.login(self.office)
        response = self.client.post(
            reverse('delete_subject_requirement', args=[self.requirement.pk]), {})
        self.assertRedirects(response, reverse('subject_requirement_list'))
        self.assertEqual(SubjectRequirement.objects.count(), 0)

    def test_office_user_can_auto_fill_curriculum(self):
        self.login(self.office)
        before = SubjectRequirement.objects.filter(
            institution=self.institution, admission_class='9',
        ).count()
        response = self.client.post(reverse('auto_populate_subject_requirements'), {
            'institution': self.institution.pk, 'admission_class': '9', 'group': '',
        })
        self.assertEqual(response.status_code, 302)
        after = SubjectRequirement.objects.filter(
            institution=self.institution, admission_class='9',
        ).count()
        self.assertGreater(after, before)


class SubjectAssignmentInstitutionIsolationTests(TestCase):
    """An Office clerk of Institution A never touches Institution B's rows."""

    def setUp(self):
        self.inst_a = Institution.objects.create(name='Isolated A', classes='6,9')
        self.inst_b = Institution.objects.create(name='Isolated B', classes='6,9')
        self.subject_a = Subject.objects.create(code='ISA', name='Isolated A Subject', full_marks=100)
        self.subject_b = Subject.objects.create(code='ISB', name='Isolated B Subject', full_marks=100)
        self.req_a = SubjectRequirement.objects.create(
            institution=self.inst_a, admission_class='9', subject=self.subject_a,
            requirement_type='MANDATORY',
        )
        self.req_b = SubjectRequirement.objects.create(
            institution=self.inst_b, admission_class='9', subject=self.subject_b,
            requirement_type='MANDATORY',
        )

        self.clerk = get_user_model().objects.create_user(username='iso-office', password='password')
        grant_sr(self.clerk, 'view', 'add', 'change', 'delete')
        InstitutionAccess.objects.create(
            user=self.clerk, institution=self.inst_a, department='Office',
        )
        self.exam_clerk = get_user_model().objects.create_user(username='iso-exam', password='password')
        grant_sr(self.exam_clerk, 'view')
        InstitutionAccess.objects.create(
            user=self.exam_clerk, institution=self.inst_a, department='Exam',
        )

    def login(self, user, department='Office'):
        self.client.force_login(user)
        session = self.client.session
        session['selected_institution_id'] = str(self.inst_a.pk)
        session['selected_department'] = department
        session.save()

    def test_list_shows_only_own_institution_rows(self):
        self.login(self.clerk)
        response = self.client.get(reverse('subject_requirement_list'))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn(self.subject_a.name, body)
        self.assertNotIn(self.subject_b.name, body)

    def test_list_with_other_institution_param_does_not_leak(self):
        self.login(self.clerk)
        response = self.client.get(
            reverse('subject_requirement_list'), {'institution': self.inst_b.pk},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(self.subject_b.name, response.content.decode())

    def test_view_only_user_of_a_cannot_read_b_either(self):
        self.login(self.exam_clerk, department='Exam')
        response = self.client.get(
            reverse('subject_requirement_list'), {'institution': self.inst_b.pk},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(self.subject_b.name, response.content.decode())

    def test_cannot_edit_other_institution_row(self):
        self.login(self.clerk)
        response = self.client.get(
            reverse('edit_subject_requirement', args=[self.req_b.pk]),
        )
        self.assertEqual(response.status_code, 404)
        response = self.client.post(
            reverse('edit_subject_requirement', args=[self.req_b.pk]),
            {'institution': self.inst_b.pk, 'admission_class': '9', 'group': '',
             'subject': self.subject_b.pk, 'requirement_type': 'OPTIONAL'},
        )
        self.assertEqual(response.status_code, 404)
        self.req_b.refresh_from_db()
        self.assertEqual(self.req_b.requirement_type, 'MANDATORY')

    def test_cannot_delete_other_institution_row(self):
        self.login(self.clerk)
        self.assertEqual(
            self.client.get(reverse('delete_subject_requirement', args=[self.req_b.pk])).status_code, 404)
        self.assertEqual(
            self.client.post(reverse('delete_subject_requirement', args=[self.req_b.pk]), {}).status_code, 404)
        self.assertTrue(SubjectRequirement.objects.filter(pk=self.req_b.pk).exists())

    def test_cannot_quick_update_other_institution_row(self):
        self.login(self.clerk)
        response = self.client.post(
            reverse('quick_update_requirement_type', args=[self.req_b.pk]),
            {'requirement_type': 'OPTIONAL'},
        )
        self.assertEqual(response.status_code, 404)
        self.req_b.refresh_from_db()
        self.assertEqual(self.req_b.requirement_type, 'MANDATORY')

    def test_cannot_add_for_other_institution(self):
        self.login(self.clerk)
        before = SubjectRequirement.objects.count()
        response = self.client.post(reverse('add_subject_requirement'), {
            'institution': self.inst_b.pk, 'admission_class': '9', 'group': '',
            'subject': self.subject_b.pk, 'requirement_type': 'MANDATORY',
        })
        self.assertEqual(response.status_code, 200)  # form re-rendered with an error
        self.assertEqual(SubjectRequirement.objects.count(), before)

    def test_cannot_auto_fill_other_institution(self):
        self.login(self.clerk)
        response = self.client.post(reverse('auto_populate_subject_requirements'), {
            'institution': self.inst_b.pk, 'admission_class': '9', 'group': '',
        })
        # Denied with a message + redirect back to the list — no 500, no rows.
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            SubjectRequirement.objects.filter(institution=self.inst_b).count(), 1,
        )
