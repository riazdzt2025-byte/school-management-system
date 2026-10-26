"""Mark Evaluation — the Group picker must only offer a group it can keep.

Reported bug (2026-10-26): on Mark Evaluation Settings, picking "Science"
for a class that has no groups reloaded the page straight back to "All
groups". The dropdown was built from whatever group tag happened to sit on
the class's Subject Assignment rows, while the view then dropped the
selection again because groups only exist from class 9 upwards (and
``SubjectMarkSetting.save()`` blanks the group below that, so the value
could never have been saved either).

The rule that follows from it: **a group picker may only offer groups the
screen can actually honour.** Below class 9 the Mark Evaluation box is now
disabled (with a note), and an exam's group picker offers nothing, so no
screen invites a choice it is about to throw away.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import (
    Exam, Institution, Student, Subject, SubjectMarkSetting, SubjectRequirement,
)
from .result_utils import get_exam_group_choices


class MarkEvaluationGroupPickerTests(TestCase):
    """Group box on Mark Evaluation: offered only where a group applies."""

    def setUp(self):
        self.institution = Institution.objects.create(
            name='Group Picker School', classes='6,8,9,10',
        )
        self.user = get_user_model().objects.create_superuser(
            'mepicker', 'me@example.com', 'password',
        )
        self.client.force_login(self.user)

        self.bangla1 = Subject.objects.create(code='BAN1G', name='Bangla 1st Paper', full_marks=100)
        self.bangla2 = Subject.objects.create(code='BAN2G', name='Bangla 2nd Paper', full_marks=100)
        self.physics = Subject.objects.create(code='PHYGP', name='Physics', full_marks=100)
        self.accounting = Subject.objects.create(code='ACCGP', name='Accounting', full_marks=100)

        # Class 8 assignments carry group tags — exactly the real data that
        # made the picker offer a group the page could not keep.
        SubjectRequirement.objects.create(institution=self.institution, admission_class='8', group='', subject=self.bangla1)
        SubjectRequirement.objects.create(institution=self.institution, admission_class='8', group='', subject=self.bangla2)
        SubjectRequirement.objects.create(institution=self.institution, admission_class='8', group='SCI', subject=self.physics)
        SubjectRequirement.objects.create(institution=self.institution, admission_class='8', group='BUS', subject=self.accounting)
        # Class 9 is a real grouped class.
        SubjectRequirement.objects.create(institution=self.institution, admission_class='9', group='', subject=self.bangla1)
        SubjectRequirement.objects.create(institution=self.institution, admission_class='9', group='SCI', subject=self.physics)
        SubjectRequirement.objects.create(institution=self.institution, admission_class='9', group='BUS', subject=self.accounting)

    def _get_settings(self, admission_class, group=''):
        return self.client.get(reverse('mark_evaluation_settings'), {
            'institution': self.institution.pk,
            'admission_class': admission_class,
            'exam_type': 'SECOND_TERM',
            'group': group,
        })

    def test_class_below_9_offers_no_group(self):
        """Nothing is offered, so nothing can snap back to "All groups"."""
        response = self._get_settings('8', group='SCI')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['selected_group'], '')
        self.assertEqual(list(response.context['group_choices']), [])
        body = response.content.decode()
        self.assertNotIn('value="SCI"', body)
        self.assertNotIn('value="BUS"', body)
        # The box is disabled and says why, instead of looking broken.
        self.assertIn('disabled', body)
        self.assertIn('groups start from class 9', body)

    def test_class_below_9_shows_every_assigned_subject(self):
        """Dropping the group must not hide subjects the school assigned."""
        response = self._get_settings('8', group='SCI')
        subject_names = {row['subject'] for row in response.context['subjects_with_settings']}
        self.assertEqual(
            subject_names, {self.bangla1, self.bangla2, self.physics, self.accounting},
        )

    def test_grouped_class_keeps_the_picked_group(self):
        """Class 9 keeps working exactly as before (regression guard)."""
        response = self._get_settings('9', group='SCI')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['selected_group'], 'SCI')
        self.assertIn('value="SCI" selected', response.content.decode())
        subject_names = {row['subject'] for row in response.context['subjects_with_settings']}
        # Group-neutral Bangla plus the Science subject, not the Business one.
        self.assertEqual(subject_names, {self.bangla1, self.physics})

    def test_grouped_class_offers_only_its_assigned_groups(self):
        response = self._get_settings('9')
        codes = [code for code, _label in response.context['group_choices']]
        self.assertEqual(sorted(codes), ['BUS', 'SCI'])

    def test_saving_below_class_9_never_stores_a_group(self):
        """A save must not 500 or silently mislabel the shared setting."""
        response = self.client.post(
            f"{reverse('mark_evaluation_settings')}"
            f"?institution={self.institution.pk}&admission_class=8"
            f"&exam_type=SECOND_TERM&group=SCI",
            {'full_marks_%d' % self.bangla1.pk: '90'},
        )
        self.assertEqual(response.status_code, 302)
        setting = SubjectMarkSetting.objects.get(
            institution=self.institution, admission_class='8',
            subject=self.bangla1, exam_type='SECOND_TERM',
        )
        self.assertEqual(setting.group, '')
        self.assertEqual(setting.full_marks, 90)

    def test_saving_for_a_grouped_class_stores_the_group(self):
        response = self.client.post(
            f"{reverse('mark_evaluation_settings')}"
            f"?institution={self.institution.pk}&admission_class=9"
            f"&exam_type=SECOND_TERM&group=SCI",
            {'full_marks_%d' % self.physics.pk: '70'},
        )
        self.assertEqual(response.status_code, 302)
        setting = SubjectMarkSetting.objects.get(
            institution=self.institution, admission_class='9',
            subject=self.physics, exam_type='SECOND_TERM', group='SCI',
        )
        self.assertEqual(setting.full_marks, 70)


class ExamGroupPickerTests(TestCase):
    """The exam screens' group picker follows the same rule."""

    def setUp(self):
        self.institution = Institution.objects.create(name='Exam Picker School', classes='8,9')
        self.subject = Subject.objects.create(code='PHYEP', name='Physics', full_marks=100)
        self.bangla = Subject.objects.create(code='BANEP', name='Bangla', full_marks=100)
        for admission_class in ('8', '9'):
            SubjectRequirement.objects.create(
                institution=self.institution, admission_class=admission_class,
                group='SCI', subject=self.subject,
            )
            SubjectRequirement.objects.create(
                institution=self.institution, admission_class=admission_class,
                group='', subject=self.bangla,
            )

    def test_class_8_exam_offers_no_group(self):
        """No class-8 student carries a group, so the filter would match nobody."""
        exam = Exam.objects.create(
            name='Class 8 Second Term', exam_type='SECOND_TERM',
            institution=self.institution, admission_class='8', group='', session='2026',
        )
        self.assertEqual(get_exam_group_choices(exam), [])

    def test_class_9_exam_offers_its_assigned_groups(self):
        exam = Exam.objects.create(
            name='Class 9 Second Term', exam_type='SECOND_TERM',
            institution=self.institution, admission_class='9', group='', session='2026',
        )
        self.assertEqual(get_exam_group_choices(exam), [('SCI', 'Science')])

    def test_class_8_exam_group_filter_is_ignored(self):
        """A hand-typed ?group= on a class-8 exam cannot empty the student list."""
        user = get_user_model().objects.create_superuser('expicker', 'ex@example.com', 'password')
        self.client.force_login(user)
        exam = Exam.objects.create(
            name='Class 8 Second Term', exam_type='SECOND_TERM',
            institution=self.institution, admission_class='8', group='', session='2026',
        )
        Student.objects.create(
            institution=self.institution, student_id='EP1', name='Class Eight Student',
            admission_class='8', section='A', guardian_contact_no='01810000000',
        )
        response = self.client.get(
            reverse('select_marks_subject', args=[exam.pk]), {'group': 'SCI'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['selected_group'], '')
        self.assertFalse(response.context['show_group_picker'])
        # The group-neutral subject is still offered: the ignored group did
        # not empty the class.
        self.assertIn(self.bangla, list(response.context['subjects']))
