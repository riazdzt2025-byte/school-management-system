"""The whole "new subject -> published result" path, end to end.

Answers, with tests, the question the office actually asks:

    নতুন বিষয়ে রেজাল্ট দিতে হলে কোথায় subject add করব, কোথায় assign করব,
    কোথায় mark evaluation সেট করব এবং কোথা থেকে নম্বর দেব?

The workflow the tests pin down is the one the code already implements — no
parallel system is introduced here:

1. Subject creation happens **inline** on the Assign Subject form
   (Office -> Subject Assignments -> "+ Assign Subject"). There is no separate
   Subjects master page any more.
2. Assigning = a ``SubjectRequirement`` row for Institution + Class (+ Group).
   Nothing reaches marks entry from the Subject master list alone.
3. Optional subjects additionally need a ``StudentSubjectChoice`` per student
   (Office -> Students -> Edit student). Mandatory rows and each student's own
   religion paper are derived at read time, so they need no choice row.
4. Full marks / CQ / MCQ / Practical / pass % come from ``SubjectMarkSetting``
   (Exam -> Mark Evaluation), falling back to the Subject's own defaults.
5. Marks are entered per subject from Exam -> Enter Marks, or imported one
   subject at a time from the exam's Import page.

The last group of tests covers the risk that matters most: adding a subject
must not silently rewrite a result that was already published.
"""
from decimal import Decimal
from io import BytesIO
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

try:
    from openpyxl import Workbook, load_workbook
except ModuleNotFoundError:
    Workbook = None
    load_workbook = None

from .forms import SubjectRequirementForm
from .models import (
    Exam, ExamMark, Institution, InstitutionAccess, Student, StudentSubjectChoice,
    Subject, SubjectMarkSetting, SubjectRequirement,
)
from .permissions import ensure_default_groups, sync_user_department_permissions
from .result_utils import (
    SUBJECTS_ALL_DISABLED,
    SUBJECTS_NOT_ASSIGNED,
    SUBJECTS_NO_STUDENT,
    build_exam_results,
    published_exams_affected_by_assignment,
    subject_availability_diagnosis,
)


def user_has_perm(user, codename):
    return user.has_perm(codename)


def department_user(username, department, institution):
    """A non-admin user bound to one institution + department, with the group
    permissions ``permissions.ensure_default_groups`` gives that department."""
    ensure_default_groups()
    user = get_user_model().objects.create_user(username=username, password='pw')
    InstitutionAccess.objects.create(
        user=user, institution=institution, department=department,
    )
    sync_user_department_permissions(user)
    return user


def assign(institution, subject, admission_class='9', group='',
           requirement_type='MANDATORY', optional_set_key=''):
    return SubjectRequirement.objects.create(
        institution=institution,
        admission_class=admission_class,
        group=group,
        subject=subject,
        requirement_type=requirement_type,
        optional_set_key=optional_set_key,
    )


class SubjectCreateAndAssignTests(TestCase):
    """Step 1+2 — where a new subject is created and where it is assigned."""

    def setUp(self):
        self.institution = Institution.objects.create(name='New Subject School', classes='9,10')
        self.user = department_user('office-clerk', 'Office', self.institution)
        self.client.force_login(self.user)
        self.url = (
            f"{reverse('add_subject_requirement')}"
            f"?institution={self.institution.pk}&admission_class=9"
        )

    def _post(self, **overrides):
        payload = {
            'institution': self.institution.pk,
            'admission_class': '9',
            'group': '',
            'subject': '',
            'new_subject_code': 'STAT',
            'new_subject_name': 'Statistics',
            'new_subject_full_marks': 100,
            'new_subject_category': 'OTHER',
            'requirement_type': 'MANDATORY',
            'optional_set_key': '',
            'condition_religion': '',
        }
        payload.update(overrides)
        return self.client.post(self.url, payload, follow=True)

    def test_assign_form_creates_the_subject_and_assigns_it_in_one_step(self):
        response = self._post()
        self.assertEqual(response.status_code, 200)
        subject = Subject.objects.get(code='STAT')
        requirement = SubjectRequirement.objects.get(subject=subject)
        self.assertEqual(requirement.institution, self.institution)
        self.assertEqual(requirement.admission_class, '9')
        self.assertEqual(requirement.requirement_type, 'MANDATORY')

    def test_created_by_is_recorded_on_the_inline_created_subject(self):
        # Subject.created_by already existed but every inline-created subject
        # left it empty, so the audit trail stopped at the Subject table.
        self._post()
        self.assertEqual(Subject.objects.get(code='STAT').created_by, self.user)

    def test_duplicate_code_is_rejected(self):
        Subject.objects.create(code='STAT', name='Something Else', full_marks=100)
        self._post()
        self.assertEqual(Subject.objects.filter(code='STAT').count(), 1)
        self.assertFalse(SubjectRequirement.objects.exists())

    def test_duplicate_code_is_rejected_case_insensitively(self):
        Subject.objects.create(code='STAT', name='Something Else', full_marks=100)
        self._post(new_subject_code='stat', new_subject_name='Statistics')
        self.assertEqual(Subject.objects.count(), 1)

    def test_duplicate_name_is_rejected(self):
        # A second "Statistics" under a different code would appear twice in
        # marks entry and as two indistinguishable result columns.
        Subject.objects.create(code='126', name='Statistics', full_marks=100)
        response = self._post(new_subject_code='STAT')
        self.assertEqual(Subject.objects.count(), 1)
        self.assertFalse(SubjectRequirement.objects.exists())
        self.assertContains(response, 'already exists as code 126')

    def test_duplicate_name_error_names_the_existing_subject(self):
        Subject.objects.create(code='126', name='Statistics', full_marks=100)
        form = SubjectRequirementForm({
            'institution': self.institution.pk, 'admission_class': '9', 'group': '',
            'subject': '', 'new_subject_code': 'STAT', 'new_subject_name': 'statistics',
            'new_subject_full_marks': 100, 'new_subject_category': 'OTHER',
            'requirement_type': 'MANDATORY',
        }, user=self.user)
        self.assertFalse(form.is_valid())
        self.assertIn('126', form.errors['new_subject_name'][0])

    def test_same_subject_cannot_be_assigned_twice_to_one_class_and_group(self):
        subject = Subject.objects.create(code='STAT', name='Statistics', full_marks=100)
        assign(self.institution, subject)
        response = self.client.post(self.url, {
            'institution': self.institution.pk, 'admission_class': '9', 'group': '',
            'subject': subject.pk, 'requirement_type': 'MANDATORY',
        }, follow=True)
        # The unique constraint is validated by the ModelForm before the row
        # ever reaches the database, so the duplicate is refused and the reason
        # is shown on the form.
        self.assertEqual(SubjectRequirement.objects.filter(subject=subject).count(), 1)
        self.assertContains(response, 'already exists')
        self.assertIn('Institution', response.context['form'].errors.as_text())

    def test_same_subject_can_be_assigned_to_a_different_group(self):
        # The constraint is per Institution + Class + Group, so the same
        # subject legitimately appears for Science and for Business Studies.
        subject = Subject.objects.create(code='HMATH', name='Higher Math', full_marks=100)
        assign(self.institution, subject, group='SCI')
        self.client.post(self.url, {
            'institution': self.institution.pk, 'admission_class': '9', 'group': 'BUS',
            'subject': subject.pk, 'requirement_type': 'MANDATORY',
        }, follow=True)
        self.assertEqual(
            sorted(SubjectRequirement.objects.filter(subject=subject)
                   .values_list('group', flat=True)),
            ['BUS', 'SCI'],
        )

    def test_inline_subject_fields_are_hidden_without_add_subject_permission(self):
        # A user who may assign but not create must not be shown (or allowed to
        # post) the new-subject fields.
        user = get_user_model().objects.create_user(username='viewer', password='pw')
        from django.contrib.auth.models import Permission
        from django.contrib.contenttypes.models import ContentType
        user.user_permissions.add(Permission.objects.get(
            content_type=ContentType.objects.get_for_model(SubjectRequirement),
            codename='add_subjectrequirement',
        ))
        self.client.force_login(user)
        self.assertFalse(user.has_perm('students.add_subject'))
        response = self.client.get(self.url)
        self.assertNotContains(response, 'new_subject_code')
        self.assertContains(response, 'subject-management rights')

        posted = self.client.post(self.url, {
            'institution': self.institution.pk, 'admission_class': '9', 'group': '',
            'subject': '', 'new_subject_code': 'STAT', 'new_subject_name': 'Statistics',
            'requirement_type': 'MANDATORY',
        }, follow=True)
        self.assertFalse(Subject.objects.filter(code='STAT').exists())
        self.assertContains(posted, 'subject-management rights')


class MarkEvaluationReachabilityTests(TestCase):
    """Step 3 — the marks distribution screen has to be reachable by the
    departments that do the work. It used to 403 for every one of them."""

    def setUp(self):
        self.institution = Institution.objects.create(name='Eval School', classes='9')
        self.subject = Subject.objects.create(code='101', name='Bangla', full_marks=100)
        assign(self.institution, self.subject)
        Student.objects.create(
            institution=self.institution, student_id='E001', name='Eval Kid',
            admission_class='9', section='A', roll_no=1, admission_year=2026,
            guardian_contact_no='01812345678',
        )
        self.url = (
            f"{reverse('mark_evaluation_settings')}?institution={self.institution.pk}"
            f"&admission_class=9&exam_type=FIRST_TERM"
        )

    def test_exam_department_can_open_mark_evaluation(self):
        user = department_user('exam-officer', 'Exam', self.institution)
        self.client.force_login(user)
        self.assertTrue(user.has_perm('students.change_subject'))
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [row['subject'].pk for row in response.context['subjects_with_settings']],
            [self.subject.pk],
        )

    def test_office_department_can_open_mark_evaluation(self):
        user = department_user('office-clerk', 'Office', self.institution)
        self.client.force_login(user)
        self.assertTrue(user.has_perm('students.add_subject'))
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_sidebar_link_follows_the_permission(self):
        # Accounts enters marks but does not set the distribution, so it must
        # not be shown a link that only leads to a 403.
        accounts = department_user('accounts-clerk', 'Accounts', self.institution)
        self.client.force_login(accounts)
        body = self.client.get(reverse('dashboard')).content.decode()
        self.assertFalse(accounts.has_perm('students.change_subject'))
        self.assertNotIn(reverse('mark_evaluation_settings'), body)

        exam = department_user('exam-officer', 'Exam', self.institution)
        self.client.force_login(exam)
        body = self.client.get(reverse('dashboard')).content.decode()
        self.assertIn(reverse('mark_evaluation_settings'), body)

    def test_saving_the_distribution_sets_parts_and_pass_marks(self):
        user = department_user('exam-officer', 'Exam', self.institution)
        self.client.force_login(user)
        response = self.client.post(reverse('mark_evaluation_settings'), {
            'institution': self.institution.pk,
            'admission_class': '9',
            'exam_type': 'FIRST_TERM',
            f'full_marks_{self.subject.pk}': 100,
            f'cq_marks_{self.subject.pk}': 75,
            f'mcq_marks_{self.subject.pk}': 25,
            f'pass_percentage_{self.subject.pk}': 40,
            f'is_active_{self.subject.pk}': '1',
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        setting = SubjectMarkSetting.objects.get(subject=self.subject)
        self.assertEqual(setting.full_marks, 100)
        self.assertEqual(setting.cq_marks, 75)
        self.assertEqual(setting.mcq_marks, 25)
        self.assertEqual(setting.pass_marks, Decimal('40'))
        self.assertTrue(setting.is_active)


class NewSubjectMarksEntryTests(TestCase):
    """Steps 4+5 — the new subject reaches marks entry, and only the students
    who actually take it get a row."""

    def setUp(self):
        self.institution = Institution.objects.create(name='Marks School', classes='9,10')
        self.bangla = Subject.objects.create(code='101', name='Bangla', full_marks=100)
        assign(self.institution, self.bangla)
        self.students = [
            Student.objects.create(
                institution=self.institution, student_id=f'M00{i}', name=f'Kid {i}',
                admission_class='9', section='A', roll_no=i, admission_year=2026,
                religion='Islam', guardian_contact_no='01812345678',
            )
            for i in (1, 2)
        ]
        self.exam = Exam.objects.create(
            name='First Term 2026', exam_type='FIRST_TERM', institution=self.institution,
            admission_class='9', session='2026',
        )
        self.user = department_user('exam-officer', 'Exam', self.institution)
        self.client.force_login(self.user)

    def test_new_mandatory_subject_reaches_marks_entry_immediately(self):
        statistics = Subject.objects.create(code='STAT', name='Statistics', full_marks=100)
        assign(self.institution, statistics)
        response = self.client.get(reverse('select_marks_subject', args=[self.exam.pk]))
        offered = [s.name for s in response.context['subjects']]
        self.assertIn('Statistics', offered)

        posted = self.client.post(
            reverse('enter_marks', args=[self.exam.pk, statistics.pk]),
            {f'marks_{student.pk}': 70 for student in self.students},
            follow=True,
        )
        self.assertEqual(posted.status_code, 200)
        self.assertEqual(
            ExamMark.objects.filter(exam=self.exam, subject=statistics).count(), 2,
        )

    def test_optional_subject_is_not_offered_until_a_student_chooses_it(self):
        agriculture = Subject.objects.create(code='AGRI', name='Agriculture', full_marks=100)
        requirement = assign(
            self.institution, agriculture, requirement_type='OPTIONAL', optional_set_key='group-a',
        )
        response = self.client.get(reverse('select_marks_subject', args=[self.exam.pk]))
        self.assertNotIn('Agriculture', [s.name for s in response.context['subjects']])

        # Once one student picks it, the subject appears — for that student.
        StudentSubjectChoice.objects.create(student=self.students[0], requirement=requirement)
        response = self.client.get(reverse('select_marks_subject', args=[self.exam.pk]))
        self.assertIn('Agriculture', [s.name for s in response.context['subjects']])

        page = self.client.get(reverse('enter_marks', args=[self.exam.pk, agriculture.pk]))
        rows = {row['student'].pk: row['sits_subject'] for row in page.context['students_with_marks']}
        self.assertTrue(rows[self.students[0].pk])
        self.assertFalse(rows[self.students[1].pk])

    def test_marks_for_a_subject_assigned_to_another_class_are_refused(self):
        class_ten_subject = Subject.objects.create(code='PHY10', name='Physics 10', full_marks=100)
        assign(self.institution, class_ten_subject, admission_class='10')
        response = self.client.get(
            reverse('enter_marks', args=[self.exam.pk, class_ten_subject.pk]),
        )
        self.assertRedirects(response, reverse('select_marks_subject', args=[self.exam.pk]))
        self.assertFalse(ExamMark.objects.filter(subject=class_ten_subject).exists())

    def test_marks_for_another_institutions_subject_are_refused(self):
        other = Institution.objects.create(name='Other School', classes='9')
        other_subject = Subject.objects.create(code='OTH', name='Other Subject', full_marks=100)
        assign(other, other_subject)
        response = self.client.get(
            reverse('enter_marks', args=[self.exam.pk, other_subject.pk]),
        )
        self.assertRedirects(response, reverse('select_marks_subject', args=[self.exam.pk]))
        self.assertFalse(ExamMark.objects.filter(subject=other_subject).exists())

    def test_marks_are_rejected_for_a_student_who_does_not_take_the_subject(self):
        agriculture = Subject.objects.create(code='AGRI', name='Agriculture', full_marks=100)
        requirement = assign(
            self.institution, agriculture, requirement_type='OPTIONAL', optional_set_key='group-a',
        )
        StudentSubjectChoice.objects.create(student=self.students[0], requirement=requirement)
        # Posted for both students; only the one who chose it may be saved.
        self.client.post(
            reverse('enter_marks', args=[self.exam.pk, agriculture.pk]),
            {f'marks_{student.pk}': 60 for student in self.students},
        )
        saved = ExamMark.objects.filter(exam=self.exam, subject=agriculture)
        self.assertEqual([mark.student_id for mark in saved], [self.students[0].pk])


class SubjectAvailabilityDiagnosisTests(TestCase):
    """The empty state must name the real cause. All three used to print the
    same "no subjects are assigned" line."""

    def setUp(self):
        self.institution = Institution.objects.create(name='Diag School', classes='9')
        self.student = Student.objects.create(
            institution=self.institution, student_id='D001', name='Diag Kid',
            admission_class='9', section='A', roll_no=1, admission_year=2026,
            guardian_contact_no='01812345678',
        )
        self.exam = Exam.objects.create(
            name='First Term 2026', exam_type='FIRST_TERM', institution=self.institution,
            admission_class='9', session='2026',
        )

    def test_not_assigned(self):
        reason, message = subject_availability_diagnosis(self.exam)
        self.assertEqual(reason, SUBJECTS_NOT_ASSIGNED)
        self.assertIn('No subjects are assigned to Class 9', message)
        self.assertIn('Subject Assignments', message)

    def test_all_disabled_in_mark_evaluation_points_at_mark_evaluation(self):
        bangla = Subject.objects.create(code='101', name='Bangla', full_marks=100)
        assign(self.institution, bangla)
        SubjectMarkSetting.objects.create(
            institution=self.institution, admission_class='9', subject=bangla,
            exam_type='FIRST_TERM', full_marks=100, is_active=False,
        )
        reason, message = subject_availability_diagnosis(self.exam)
        self.assertEqual(reason, SUBJECTS_ALL_DISABLED)
        self.assertIn('Mark Evaluation', message)
        # The old generic line would have sent the user to the wrong page.
        self.assertNotIn('No subjects are assigned', message)

    def test_unchosen_optional_points_at_the_student_subject_choice(self):
        agriculture = Subject.objects.create(code='AGRI', name='Agriculture', full_marks=100)
        assign(self.institution, agriculture, requirement_type='OPTIONAL')
        reason, message = subject_availability_diagnosis(self.exam)
        self.assertEqual(reason, SUBJECTS_NO_STUDENT)
        self.assertIn('subject choice', message)

    def test_page_offers_no_link_the_user_cannot_use(self):
        from .views import subject_help_context
        bangla = Subject.objects.create(code='101', name='Bangla', full_marks=100)
        assign(self.institution, bangla)
        SubjectMarkSetting.objects.create(
            institution=self.institution, admission_class='9', subject=bangla,
            exam_type='FIRST_TERM', full_marks=100, is_active=False,
        )

        # An Exam user may fix this: link, no "ask someone else".
        exam_user = department_user('exam-officer', 'Exam', self.institution)
        request = type('R', (), {'user': exam_user})()
        help_context = subject_help_context(request, self.exam)
        self.assertEqual(help_context['reason'], SUBJECTS_ALL_DISABLED)
        self.assertIn(reverse('mark_evaluation_settings'), help_context['action_url'])
        self.assertEqual(help_context['contact_department'], '')

        # An Accounts user may not: no link, and the owning department is named.
        accounts_user = department_user('accounts-clerk', 'Accounts', self.institution)
        request = type('R', (), {'user': accounts_user})()
        help_context = subject_help_context(request, self.exam)
        self.assertEqual(help_context['action_url'], '')
        self.assertIn('Exam', help_context['contact_department'])

    def test_marks_entry_page_prints_the_mark_evaluation_cause(self):
        bangla = Subject.objects.create(code='101', name='Bangla', full_marks=100)
        assign(self.institution, bangla)
        SubjectMarkSetting.objects.create(
            institution=self.institution, admission_class='9', subject=bangla,
            exam_type='FIRST_TERM', full_marks=100, is_active=False,
        )
        user = department_user('exam-officer', 'Exam', self.institution)
        self.client.force_login(user)
        response = self.client.get(reverse('select_marks_subject', args=[self.exam.pk]))
        self.assertEqual(response.context['subject_help']['reason'], SUBJECTS_ALL_DISABLED)
        self.assertContains(response, 'switched off in Mark Evaluation')
        self.assertContains(response, reverse('mark_evaluation_settings'))


@skipUnless(Workbook, 'openpyxl is not installed')
class NewSubjectExcelImportTests(TestCase):
    """The Excel template and import follow the same subject scoping."""

    def setUp(self):
        self.institution = Institution.objects.create(name='Import School', classes='9')
        self.subject = Subject.objects.create(code='STAT', name='Statistics', full_marks=100)
        assign(self.institution, self.subject)
        self.student = Student.objects.create(
            institution=self.institution, student_id='I001', name='Import Kid',
            admission_class='9', section='A', roll_no=1, admission_year=2026,
            guardian_contact_no='01812345678',
        )
        self.exam = Exam.objects.create(
            name='First Term 2026', exam_type='FIRST_TERM', institution=self.institution,
            admission_class='9', session='2026',
        )
        self.client.force_login(department_user('exam-officer', 'Exam', self.institution))

    def test_template_download_then_import_round_trip(self):
        template = self.client.get(
            reverse('download_marks_import_template', args=[self.exam.pk]),
            {'subject': self.subject.pk},
        )
        self.assertEqual(template.status_code, 200)
        workbook = load_workbook(BytesIO(template.content))
        sheet = workbook.worksheets[0]
        headers = [cell.value for cell in sheet[1]]
        self.assertEqual(headers, ['Roll', 'ID', 'Name', 'Marks'])

        sheet.cell(row=2, column=1, value=1)
        sheet.cell(row=2, column=2, value=self.student.student_id)
        sheet.cell(row=2, column=3, value=self.student.name)
        sheet.cell(row=2, column=4, value=72)
        buffer = BytesIO()
        workbook.save(buffer)
        buffer.seek(0)

        from django.core.files.uploadedfile import SimpleUploadedFile
        uploaded = SimpleUploadedFile(
            'statistics.xlsx', buffer.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response = self.client.post(
            reverse('import_exam_marks', args=[self.exam.pk]),
            {'subject': self.subject.pk, 'excel_file': uploaded},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        mark = ExamMark.objects.get(exam=self.exam, subject=self.subject)
        self.assertEqual(mark.marks_obtained, Decimal('72'))
        self.assertEqual(mark.student, self.student)

    def test_template_is_refused_for_a_subject_not_assigned_to_the_class(self):
        other = Subject.objects.create(code='OTH', name='Not Assigned', full_marks=100)
        response = self.client.get(
            reverse('download_marks_import_template', args=[self.exam.pk]),
            {'subject': other.pk},
        )
        self.assertRedirects(
            response, reverse('import_exam_marks', args=[self.exam.pk]),
            fetch_redirect_response=False,
        )
        followed = self.client.get(reverse('import_exam_marks', args=[self.exam.pk]))
        self.assertContains(followed, 'Pick a subject first')


class NewSubjectResultPagesTests(TestCase):
    """Step 6 — the new subject shows up on the sheet, the summary and the
    individual result card, and only after publishing."""

    def setUp(self):
        self.institution = Institution.objects.create(name='Result School', classes='9')
        self.bangla = Subject.objects.create(code='101', name='Bangla', full_marks=100)
        self.statistics = Subject.objects.create(code='STAT', name='Statistics', full_marks=100)
        assign(self.institution, self.bangla)
        assign(self.institution, self.statistics)
        self.student = Student.objects.create(
            institution=self.institution, student_id='R001', name='Result Kid',
            admission_class='9', section='A', roll_no=1, admission_year=2026,
            guardian_contact_no='01812345678',
        )
        self.exam = Exam.objects.create(
            name='First Term 2026', exam_type='FIRST_TERM', institution=self.institution,
            admission_class='9', session='2026', is_published=True,
        )
        ExamMark.objects.create(
            exam=self.exam, student=self.student, subject=self.bangla, marks_obtained=80,
        )
        ExamMark.objects.create(
            exam=self.exam, student=self.student, subject=self.statistics, marks_obtained=60,
        )
        self.client.force_login(department_user('exam-officer', 'Exam', self.institution))

    def test_result_sheet_summary_and_card_all_show_the_new_subject(self):
        sheet = self.client.get(reverse('result_sheet', args=[self.exam.pk]))
        self.assertContains(sheet, 'Statistics')
        columns = [str(column) for column in sheet.context['subjects']]
        self.assertEqual(columns, ['Bangla', 'Statistics'])

        summary = self.client.get(reverse('exam_result_summary', args=[self.exam.pk]))
        self.assertEqual(summary.status_code, 200)
        result = next(r for r in summary.context['results'] if r['student'].pk == self.student.pk)
        self.assertEqual(result['status'], 'Pass')
        self.assertEqual(result['total_obtained'], Decimal('140'))
        self.assertEqual(result['total_full'], Decimal('200'))

        card = self.client.get(reverse('result_card', args=[self.exam.pk, self.student.pk]))
        self.assertEqual(card.status_code, 200)
        self.assertContains(card, 'Statistics')

        detail = self.client.get(
            reverse('student_result_detail', args=[self.exam.pk, self.student.pk]),
        )
        self.assertContains(detail, 'Statistics')

    def test_result_pages_stay_closed_until_the_exam_is_published(self):
        self.exam.is_published = False
        self.exam.save(update_fields=['is_published'])
        for name in ('result_sheet', 'exam_result_summary'):
            response = self.client.get(reverse(name, args=[self.exam.pk]))
            self.assertRedirects(response, reverse('exam_list'))

    def test_publishing_is_a_exam_department_action(self):
        office_user = department_user('office-clerk', 'Office', self.institution)
        self.client.force_login(office_user)
        self.assertFalse(office_user.has_perm('students.change_exam'))
        response = self.client.post(reverse('toggle_publish_exam', args=[self.exam.pk]))
        self.assertEqual(response.status_code, 403)

        self.client.force_login(department_user('exam-publisher', 'Exam', self.institution))
        response = self.client.post(
            reverse('toggle_publish_exam', args=[self.exam.pk]), follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.exam.refresh_from_db()
        self.assertFalse(self.exam.is_published)


class PublishedResultSafetyTests(TestCase):
    """Step 7 — a new subject must not quietly rewrite an older result.

    Adding a subject to a class is read at result time, so it reaches exams
    that were published earlier too. An *optional* subject is safe: it only
    counts for the students who chose it. A *mandatory* one is not — with
    EXAM_ABSENT_SUBJECT_FAILS on, a blank column fails every student in it, so
    the screens warn about it instead of staying quiet.
    """

    def setUp(self):
        self.institution = Institution.objects.create(name='History School', classes='9')
        self.bangla = Subject.objects.create(code='101', name='Bangla', full_marks=100)
        assign(self.institution, self.bangla)
        self.students = [
            Student.objects.create(
                institution=self.institution, student_id=f'H00{i}', name=f'Old Kid {i}',
                admission_class='9', section='A', roll_no=i, admission_year=2026,
                religion='Islam', guardian_contact_no='01812345678',
            )
            for i in (1, 2)
        ]
        self.exam = Exam.objects.create(
            name='First Term 2026', exam_type='FIRST_TERM', institution=self.institution,
            admission_class='9', session='2026', is_published=True,
        )
        for student in self.students:
            ExamMark.objects.create(
                exam=self.exam, student=student, subject=self.bangla, marks_obtained=80,
            )
        self.user = department_user('office-clerk', 'Office', self.institution)
        self.client.force_login(self.user)

    def _results_by_student(self):
        _columns, results = build_exam_results(self.exam)
        return {
            result['student'].pk: (
                result['status'], str(result['gpa']),
                result['total_obtained'], result['total_full'],
            )
            for result in results
        }

    def test_adding_an_optional_subject_leaves_the_published_result_untouched(self):
        before = self._results_by_student()
        self.assertEqual(
            set(before.values()), {('Pass', '5.00', Decimal('80.00'), Decimal('100'))},
        )

        agriculture = Subject.objects.create(code='AGRI', name='Agriculture', full_marks=100)
        assign(self.institution, agriculture, requirement_type='OPTIONAL', optional_set_key='g')

        self.assertEqual(self._results_by_student(), before)
        # And nobody is failed for a paper they never sat.
        sheet = self.client.get(reverse('result_sheet', args=[self.exam.pk]))
        self.assertEqual(sheet.context['missing_mark_subjects'], [])
        # An optional subject nobody chose is not even reported as unmarked:
        # it was never this exam's subject to begin with.
        self.assertEqual(sheet.context['unmarked_subjects'], [])

    def test_a_new_mandatory_subject_leaves_the_published_result_unchanged(self):
        # The rule that replaced the old one: a subject the exam holds no mark
        # for at all is not a column, so assigning it after publication cannot
        # rewrite the result. Before this, both students went Pass 5.00 ->
        # Fail 0.00 on an empty Statistics column.
        before = self._results_by_student()
        self.assertEqual(
            set(before.values()), {('Pass', '5.00', Decimal('80.00'), Decimal('100'))},
        )
        statistics = Subject.objects.create(code='STAT', name='Statistics', full_marks=100)
        assign(self.institution, statistics)

        self.assertEqual(self._results_by_student(), before)
        _columns, results = build_exam_results(self.exam)
        self.assertEqual(
            [[str(sr['subject']) for sr in r['subject_results']] for r in results],
            [['Bangla'], ['Bangla']],
        )

    def test_the_unmarked_subject_becomes_a_column_once_marks_are_entered(self):
        statistics = Subject.objects.create(code='STAT', name='Statistics', full_marks=100)
        assign(self.institution, statistics)
        ExamMark.objects.create(
            exam=self.exam, student=self.students[0], subject=statistics, marks_obtained=55,
        )
        columns, _results = build_exam_results(self.exam)
        self.assertEqual([str(column) for column in columns], ['Bangla', 'Statistics'])
        # The student with no Statistics mark is failed by it; the one with a
        # mark is not. Individual absence still counts.
        by_student = self._results_by_student()
        self.assertEqual(by_student[self.students[0].pk][0], 'Pass')
        self.assertEqual(by_student[self.students[1].pk][0], 'Fail')

    def test_result_sheet_names_the_subject_it_left_out(self):
        statistics = Subject.objects.create(code='STAT', name='Statistics', full_marks=100)
        assign(self.institution, statistics)
        response = self.client.get(reverse('result_sheet', args=[self.exam.pk]))
        self.assertEqual(
            [str(subject) for subject in response.context['unmarked_subjects']],
            ['Statistics'],
        )
        self.assertContains(response, 'no marks at all')
        # A subject left out for want of marks is not also reported as a
        # partially-entered one.
        self.assertEqual(response.context['missing_mark_subjects'], [])

    def test_result_sheet_names_students_missing_from_an_entered_subject(self):
        statistics = Subject.objects.create(code='STAT', name='Statistics', full_marks=100)
        assign(self.institution, statistics)
        ExamMark.objects.create(
            exam=self.exam, student=self.students[0], subject=statistics, marks_obtained=55,
        )
        response = self.client.get(reverse('result_sheet', args=[self.exam.pk]))
        self.assertEqual(response.context['unmarked_subjects'], [])
        missing = response.context['missing_mark_subjects']
        self.assertEqual(len(missing), 1)
        self.assertEqual(str(missing[0]['subject']), 'Statistics')
        self.assertEqual(missing[0]['count'], 1)
        self.assertContains(response, 'Some students have no mark')

    def test_assignment_pages_warn_about_the_affected_published_exams(self):
        affected = published_exams_affected_by_assignment(
            self.institution.pk, '9',
        )
        self.assertEqual([exam.pk for exam in affected], [self.exam.pk])

        listing = self.client.get(
            f"{reverse('subject_requirement_list')}?institution={self.institution.pk}"
            f"&admission_class=9",
        )
        self.assertEqual(
            [exam.pk for exam in listing.context['affected_exams']], [self.exam.pk],
        )
        self.assertContains(listing, 'Published results for this class already exist')

        add_page = self.client.get(
            f"{reverse('add_subject_requirement')}?institution={self.institution.pk}"
            f"&admission_class=9",
        )
        self.assertContains(add_page, 'This class already has published results')

        evaluation_page = self.client.get(
            f"{reverse('mark_evaluation_settings')}?institution={self.institution.pk}"
            f"&admission_class=9&exam_type=FIRST_TERM",
        )
        self.assertEqual(
            [exam.pk for exam in evaluation_page.context['affected_exams']], [self.exam.pk],
        )

    def test_unpublished_exam_is_not_reported_as_affected(self):
        self.exam.is_published = False
        self.exam.save(update_fields=['is_published'])
        self.assertEqual(
            published_exams_affected_by_assignment(self.institution.pk, '9'), [],
        )

    def test_other_institution_and_class_are_not_reported(self):
        other = Institution.objects.create(name='Elsewhere', classes='9')
        self.assertEqual(published_exams_affected_by_assignment(other.pk, '9'), [])
        self.assertEqual(
            published_exams_affected_by_assignment(self.institution.pk, '10'), [],
        )


class SubjectWorkflowGuidanceTests(TestCase):
    """The navigation itself: the steps are described where the work starts,
    and only for the user who can actually do them."""

    def setUp(self):
        self.institution = Institution.objects.create(name='Guide School', classes='9')
        self.subject = Subject.objects.create(code='101', name='Bangla', full_marks=100)
        assign(self.institution, self.subject)

    def test_office_user_sees_the_whole_workflow(self):
        self.user = department_user('office-clerk', 'Office', self.institution)
        self.client.force_login(self.user)
        response = self.client.get(
            f"{reverse('subject_requirement_list')}?institution={self.institution.pk}"
            f"&admission_class=9",
        )
        body = response.content.decode()
        self.assertIn('Getting a new subject onto a result sheet', body)
        self.assertIn(reverse('mark_evaluation_settings'), body)
        # Office assigns subjects, so the assign action is a real link.
        self.assertIn(reverse('add_subject_requirement'), body)
        # ...but it does not enter marks, so that step names the department
        # instead of linking to a page that would 403.
        self.assertFalse(user_has_perm(self.user, 'students.add_exammark'))
        self.assertIn('ask the <strong>Exam</strong> (or Accounts) department', body)

    def test_exam_user_is_told_who_assigns_subjects(self):
        user = department_user('exam-officer', 'Exam', self.institution)
        self.client.force_login(user)
        response = self.client.get(
            f"{reverse('subject_requirement_list')}?institution={self.institution.pk}"
            f"&admission_class=9",
        )
        body = response.content.decode()
        self.assertIn('Getting a new subject onto a result sheet', body)
        self.assertIn('ask the <strong>Office</strong> department', body)
        # Exam does hold the marks permissions, so those steps stay live links.
        self.assertIn(reverse('mark_evaluation_settings'), body)
        self.assertIn(reverse('start_entering_marks'), body)

    def test_mark_evaluation_empty_state_links_to_the_assignments_page(self):
        self.client.force_login(department_user('office-clerk', 'Office', self.institution))
        SubjectRequirement.objects.all().delete()
        response = self.client.get(
            f"{reverse('mark_evaluation_settings')}?institution={self.institution.pk}"
            f"&admission_class=9&exam_type=FIRST_TERM",
        )
        self.assertEqual(response.context['empty_reason'], SUBJECTS_NOT_ASSIGNED)
        self.assertContains(response, 'Go to Subject Assignments')
        self.assertContains(response, reverse('subject_requirement_list'))
        # The stale "Subject Requirements" page name is gone.
        self.assertNotContains(response, 'Subject Requirements')

    def test_mark_evaluation_lists_assigned_subjects_before_any_student_exists(self):
        # Regression: the page used to narrow the assigned list to the subjects
        # current students take, so a brand-new assignment on a class without
        # students — or an optional subject nobody chose, or a group paper with
        # no student in that group — stayed invisible here until someone
        # enrolled/chose it. Configuration must not depend on enrollment.
        self.client.force_login(department_user('exam-officer', 'Exam', self.institution))
        self.assertFalse(Student.objects.filter(institution=self.institution).exists())
        optional = Subject.objects.create(code='102', name='Extra Optional', full_marks=100)
        assign(self.institution, optional, requirement_type='OPTIONAL',
               optional_set_key='SET1')
        grouped = Subject.objects.create(code='103', name='Group Paper', full_marks=100)
        assign(self.institution, grouped, group='SCI')
        agriculture = Subject.objects.create(code='104', name='Agriculture', full_marks=100)
        assign(self.institution, agriculture, group='BUS')

        url = (
            f"{reverse('mark_evaluation_settings')}?institution={self.institution.pk}"
            f"&admission_class=9&exam_type=FIRST_TERM"
        )
        response = self.client.get(url)
        rows = response.context['subjects_with_settings']
        self.assertEqual(
            [row['subject'].name for row in rows],
            ['Bangla', 'Extra Optional', 'Group Paper', 'Agriculture'],
        )

        # Group-based view: a group shows its own subjects plus the
        # group-neutral ones — the Business Studies paper appears under
        # Business Studies, and never under Science.
        sci = self.client.get(f"{url}&group=SCI").context['subjects_with_settings']
        self.assertEqual(
            [row['subject'].name for row in sci],
            ['Bangla', 'Extra Optional', 'Group Paper'],
        )
        bus = self.client.get(f"{url}&group=BUS")
        self.assertEqual(
            [row['subject'].name for row in bus.context['subjects_with_settings']],
            ['Bangla', 'Extra Optional', 'Agriculture'],
        )
        self.assertEqual(
            [code for code, _ in bus.context['group_choices']], ['SCI', 'BUS'],
        )
        self.assertContains(bus, 'Business Studies')
        notes = {row['subject'].name: row['groups_note'] for row in rows}
        self.assertEqual(notes['Bangla'], '')
        self.assertEqual(notes['Group Paper'], 'Science')
        self.assertContains(response, 'Science')

    def test_assign_page_hides_the_new_subject_box_without_the_permission(self):
        user = department_user('exam-officer', 'Exam', self.institution)
        self.client.force_login(user)
        self.assertFalse(user.has_perm('students.add_subjectrequirement'))
        self.assertEqual(
            self.client.get(reverse('add_subject_requirement')).status_code, 403,
        )

    def test_enter_marks_landing_page_carries_the_same_guidance(self):
        # The subject dropdown on this page is filled by JS, so the guidance
        # has to be shipped with the page and gated on the same permissions.
        self.client.force_login(department_user('exam-officer', 'Exam', self.institution))
        response = self.client.get(reverse('start_entering_marks'))
        body = response.content.decode()
        self.assertIn('showSubjectsHelp', body)
        self.assertIn(reverse('subject_requirement_list'), body)
        self.assertIn(reverse('mark_evaluation_settings'), body)
        self.assertIn('var canAssign = false', body)
        self.assertIn('var canEvaluate = true', body)

    def test_office_user_is_not_shown_the_marks_pages_it_cannot_open(self):
        # Office assigns subjects but does not enter marks, so Enter Marks must
        # not appear in its sidebar at all.
        user = department_user('office-clerk', 'Office', self.institution)
        self.client.force_login(user)
        body = self.client.get(reverse('dashboard')).content.decode()
        self.assertNotIn(reverse('start_entering_marks'), body)
        self.assertEqual(
            self.client.get(reverse('start_entering_marks')).status_code, 403,
        )
        # Mark Evaluation is reachable now, and appears in both menus.
        self.assertIn(reverse('mark_evaluation_settings'), body)

    def test_diagnosis_names_the_exam_type(self):
        # A user has to be able to tell *which* exam type switched the subject
        # off, because Mark Evaluation is configured per exam type.
        SubjectMarkSetting.objects.create(
            institution=self.institution, admission_class='9', subject=self.subject,
            exam_type='MID_TERM_1', full_marks=100, is_active=False,
        )
        exam = Exam.objects.create(
            name='Mid Term-1 2026', exam_type='MID_TERM_1', institution=self.institution,
            admission_class='9', session='2026',
        )
        _reason, message = subject_availability_diagnosis(exam)
        self.assertIn('Mid Term-1', message)
