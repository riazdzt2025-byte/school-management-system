"""SEC-FU-2: which permission groups a clerk keeps after login.

Decision (kept as an intentional limit): a non-admin clerk can only sign in
through the three login departments Office, Exam and Accounts, so login mirrors
exactly those access rows into Django groups (Office also brings Admission).
The HR, Subjects and Audit groups are never granted by login; membership added
by hand in the admin is removed at the next login. Admin/staff accounts are not
touched and use those groups directly.
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from .models import Institution, InstitutionAccess
from .permissions import sync_user_department_permissions

MANAGED = ['Office', 'Admission', 'Subjects', 'Exam', 'HR', 'Accounts', 'Audit']


class DepartmentGroupSyncTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.institution = Institution.objects.create(name='Sync Institution', classes='1,2')
        cls.user_model = get_user_model()

    def _clerk(self, username, departments=(), **extra):
        user = self.user_model.objects.create_user(username=username, password='password', **extra)
        for department in departments:
            InstitutionAccess.objects.create(
                user=user, institution=self.institution, department=department, is_active=True,
            )
        return user

    def _groups(self, user):
        return set(user.groups.values_list('name', flat=True))

    def test_all_managed_groups_exist(self):
        self.assertEqual(set(Group.objects.filter(name__in=MANAGED).values_list('name', flat=True)), set(MANAGED))

    def test_office_access_grants_office_and_admission(self):
        user = self._clerk('office-clerk', ['Office'])
        sync_user_department_permissions(user)
        self.assertEqual(self._groups(user), {'Office', 'Admission'})

    def test_exam_and_accounts_access_grant_their_own_group(self):
        exam = self._clerk('exam-clerk', ['Exam'])
        accounts = self._clerk('accounts-clerk', ['Accounts'])
        sync_user_department_permissions(exam)
        sync_user_department_permissions(accounts)
        self.assertEqual(self._groups(exam), {'Exam'})
        self.assertEqual(self._groups(accounts), {'Accounts'})

    def test_two_departments_grant_both_groups(self):
        user = self._clerk('two-depts', ['Exam', 'Accounts'])
        sync_user_department_permissions(user)
        self.assertEqual(self._groups(user), {'Exam', 'Accounts'})

    def test_deactivated_access_removes_the_group(self):
        user = self._clerk('deactivated', ['Exam'])
        sync_user_department_permissions(user)
        InstitutionAccess.objects.filter(user=user).update(is_active=False)
        sync_user_department_permissions(user)
        self.assertEqual(self._groups(user), set())

    def test_hr_subjects_audit_membership_is_removed_for_a_clerk(self):
        user = self._clerk('manual-groups', ['Office'])
        user.groups.add(*Group.objects.filter(name__in=['HR', 'Subjects', 'Audit']))
        sync_user_department_permissions(user)
        self.assertEqual(self._groups(user), {'Office', 'Admission'})

    def test_login_applies_the_same_rule(self):
        user = self._clerk('login-strip', ['Exam'])
        user.groups.add(Group.objects.get(name='HR'))
        response = self.client.post(reverse('login'), {
            'username': 'login-strip', 'password': 'password',
            'institution_id': self.institution.pk, 'department': 'Exam',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self._groups(user), {'Exam'})

    def test_staff_and_superusers_keep_their_groups(self):
        staff = self._clerk('staff-hr', is_staff=True)
        admin = self._clerk('super-audit', is_superuser=True)
        staff.groups.add(Group.objects.get(name='HR'))
        admin.groups.add(Group.objects.get(name='Audit'))
        sync_user_department_permissions(staff)
        sync_user_department_permissions(admin)
        self.assertEqual(self._groups(staff), {'HR'})
        self.assertEqual(self._groups(admin), {'Audit'})

    def test_login_departments_are_only_office_exam_accounts(self):
        self.assertEqual(
            [value for value, _ in InstitutionAccess.DEPARTMENT_CHOICES],
            ['Office', 'Exam', 'Accounts'],
        )
