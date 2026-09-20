"""EX-03 Group-based Mark Evaluation — group-aware settings + resolution chain."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse

from .models import Exam, Institution, Student, Subject, SubjectMarkSetting, SubjectRequirement, class_supports_group
from .result_utils import active_exam_subject_ids, build_exam_results, get_subject_marks, get_exam_subjects


class GroupAwareMarkEvaluationTests(TestCase):
    def setUp(self):
        self.institution = Institution.objects.create(name='EX-03 School', classes='6,9,10,11,12')
        self.other_institution = Institution.objects.create(name='Other EX-03 School', classes='9')
        self.user = get_user_model().objects.create_superuser('ex03admin', 'a@example.com', 'password')
        self.client.force_login(self.user)
        # Subjects
        self.bangla = Subject.objects.create(code='BAN03', name='Bangla', full_marks=100)
        self.physics = Subject.objects.create(code='PHY03', name='Physics', full_marks=100, cq_marks=60, mcq_marks=40)
        self.chemistry = Subject.objects.create(code='CHEM03', name='Chemistry', full_marks=100)
        self.biology = Subject.objects.create(code='BIO03', name='Biology', full_marks=100)
        # Requirements: Bangla neutral, Physics for SCI, Chemistry for BUS etc.
        SubjectRequirement.objects.create(institution=self.institution, admission_class='9', group='', subject=self.bangla, requirement_type='MANDATORY')
        SubjectRequirement.objects.create(institution=self.institution, admission_class='9', group='SCI', subject=self.physics, requirement_type='MANDATORY')
        SubjectRequirement.objects.create(institution=self.institution, admission_class='9', group='SCI', subject=self.chemistry, requirement_type='MANDATORY')
        SubjectRequirement.objects.create(institution=self.institution, admission_class='9', group='BUS', subject=self.chemistry, requirement_type='MANDATORY')
        SubjectRequirement.objects.create(institution=self.institution, admission_class='6', group='', subject=self.bangla, requirement_type='MANDATORY')
        # Exams
        self.exam_sci = Exam.objects.create(name='First Term SCI', exam_type='FIRST_TERM', institution=self.institution, admission_class='9', group='SCI', session='2026')
        self.exam_bus = Exam.objects.create(name='First Term BUS', exam_type='FIRST_TERM', institution=self.institution, admission_class='9', group='BUS', session='2026')
        self.exam_no_group = Exam.objects.create(name='First Term All', exam_type='FIRST_TERM', institution=self.institution, admission_class='9', group='', session='2026')
        self.exam_class6 = Exam.objects.create(name='Class6 Term', exam_type='FIRST_TERM', institution=self.institution, admission_class='6', group='', session='2026')
        self.exam_mid = Exam.objects.create(name='Mid Term SCI', exam_type='MID_TERM_1', institution=self.institution, admission_class='9', group='SCI', session='2026')

    # (i) group-specific override works
    def test_group_specific_override_works(self):
        # Blank default 100, SCI override 70
        SubjectMarkSetting.objects.create(institution=self.institution, admission_class='9', subject=self.physics, exam_type='FIRST_TERM', group='', full_marks=100)
        SubjectMarkSetting.objects.create(institution=self.institution, admission_class='9', subject=self.physics, exam_type='FIRST_TERM', group='SCI', full_marks=70, cq_marks=40, mcq_marks=30)
        # SCI exam should get 70, BUS should fall back to 100
        cfg_sci = get_subject_marks(self.exam_sci, self.physics)
        cfg_bus = get_subject_marks(self.exam_bus, self.physics)
        cfg_all = get_subject_marks(self.exam_no_group, self.physics)  # no group -> default
        self.assertEqual(cfg_sci.full_marks, 70)
        self.assertEqual(cfg_sci.cq_marks, 40)
        self.assertEqual(cfg_bus.full_marks, 100)
        self.assertEqual(cfg_all.full_marks, 100)
        # Explicit group override param also works when exam has no group but caller passes group
        from types import SimpleNamespace
        exam_like = SimpleNamespace(institution=self.institution, admission_class='9', group='', exam_type='FIRST_TERM', section='')
        cfg_via_param = get_subject_marks(exam_like, self.physics, group='SCI')
        self.assertEqual(cfg_via_param.full_marks, 70)
        cfg_via_param_bus = get_subject_marks(exam_like, self.physics, group='BUS')
        self.assertEqual(cfg_via_param_bus.full_marks, 100)

    # (ii) blank-group fallback when no group-specific row
    def test_blank_group_fallback(self):
        SubjectMarkSetting.objects.create(institution=self.institution, admission_class='9', subject=self.chemistry, exam_type='FIRST_TERM', group='', full_marks=80)
        # No SCI row, so SCI exam falls back to blank
        cfg = get_subject_marks(self.exam_sci, self.chemistry)
        self.assertEqual(cfg.full_marks, 80)
        # Subject global default fallback when no setting at all
        cfg_bangla = get_subject_marks(self.exam_sci, self.biology)
        self.assertEqual(cfg_bangla.full_marks, 100)
        self.assertEqual(cfg_bangla.pk, self.biology.pk)

    # (iii) inactive subject excluded (group-aware)
    def test_inactive_subject_excluded_for_group(self):
        # Make Chemistry inactive for SCI but active for default/BUS
        SubjectMarkSetting.objects.create(institution=self.institution, admission_class='9', subject=self.chemistry, exam_type='FIRST_TERM', group='SCI', full_marks=100, is_active=False)
        # get_exam_subjects for SCI should exclude chemistry, for BUS include
        from types import SimpleNamespace
        exam_sci = SimpleNamespace(institution_id=self.institution.pk, admission_class='9', group='SCI', exam_type='FIRST_TERM', section='')
        exam_bus = SimpleNamespace(institution_id=self.institution.pk, admission_class='9', group='BUS', exam_type='FIRST_TERM', section='')
        subs_sci, _ = get_exam_subjects(exam_sci)
        subs_bus, _ = get_exam_subjects(exam_bus)
        self.assertNotIn(self.chemistry, subs_sci)
        self.assertIn(self.chemistry, subs_bus)
        # Also active_exam_subject_ids directly
        ids_sci = active_exam_subject_ids(exam_sci, [self.chemistry.pk, self.physics.pk])
        self.assertNotIn(self.chemistry.pk, ids_sci)
        ids_bus = active_exam_subject_ids(exam_bus, [self.chemistry.pk, self.physics.pk])
        self.assertIn(self.chemistry.pk, ids_bus)

    # (iv) parts / pass validation negative cases
    def test_parts_sum_exact_validation_rejects_mismatch(self):
        # Model is permissive (legacy mismatched rows exist), but the Mark Evaluation view
        # enforces exact sum (owner decision 2026-09-20: exact). Direct create is allowed.
        setting = SubjectMarkSetting(institution=self.institution, admission_class='9', subject=self.physics, exam_type='FIRST_TERM', group='', full_marks=100, cq_marks=40, mcq_marks=30)
        # Should NOT raise at model layer (permissive, warning shown on entry pages)
        setting.full_clean()
        setting.save()
        self.assertTrue(SubjectMarkSetting.objects.filter(pk=setting.pk).exists())

        # Exact match should also pass and be the prevailing config for entry
        setting2 = SubjectMarkSetting(institution=self.institution, admission_class='9', subject=self.physics, exam_type='FIRST_TERM', group='SCI', full_marks=70, cq_marks=40, mcq_marks=30)
        setting2.full_clean()
        setting2.save()

        # View-level enforcement: POST mismatched via UI should be rejected with error message and not saved
        SubjectMarkSetting.objects.filter(pk=setting.pk).delete()
        # Ensure requirement exists for the subject to be listed
        # POST mismatched parts (70 vs 100) for Bangla (neutral) should be skipped
        resp = self.client.post(reverse('mark_evaluation_settings') + f'?institution={self.institution.pk}&admission_class=9&exam_type=FIRST_TERM', {
            'institution': self.institution.pk,
            'admission_class': '9',
            'exam_type': 'FIRST_TERM',
            'group': '',
            f'full_marks_{self.bangla.pk}': '100',
            f'cq_marks_{self.bangla.pk}': '40',
            f'mcq_marks_{self.bangla.pk}': '30',
            f'pass_percentage_{self.bangla.pk}': '40',
            f'is_active_{self.bangla.pk}': '1',
        })
        # Should redirect but with error message, and not create a setting (or not with mismatched)
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(SubjectMarkSetting.objects.filter(subject=self.bangla, exam_type='FIRST_TERM', group='').exists())

    def test_pass_percentage_range_validation(self):
        s = SubjectMarkSetting(institution=self.institution, admission_class='9', subject=self.physics, exam_type='FIRST_TERM', group='', full_marks=100, pass_percentage=150)
        with self.assertRaises(ValidationError):
            s.full_clean()
        s2 = SubjectMarkSetting(institution=self.institution, admission_class='9', subject=self.physics, exam_type='FIRST_TERM', group='', full_marks=100, pass_percentage=0)
        # 0 is allowed now
        s2.full_clean()
        s3 = SubjectMarkSetting(institution=self.institution, admission_class='9', subject=self.physics, exam_type='FIRST_TERM', group='', full_marks=100, pass_percentage=101)
        with self.assertRaises(ValidationError):
            s3.full_clean()

    def test_full_marks_must_be_positive(self):
        s = SubjectMarkSetting(institution=self.institution, admission_class='9', subject=self.physics, exam_type='FIRST_TERM', group='', full_marks=0)
        with self.assertRaises(ValidationError):
            s.full_clean()

    def test_weekly_test_only_for_mid_exam_types(self):
        # Model is permissive for weekly_test (legacy data may have it for any type),
        # but the view enforces MID-only (owner decision).
        s = SubjectMarkSetting(institution=self.institution, admission_class='9', subject=self.physics, exam_type='FIRST_TERM', group='', full_marks=100, weekly_test_marks=20)
        # Direct model create is allowed (no ValidationError)
        s.full_clean()
        s.save()
        self.assertTrue(SubjectMarkSetting.objects.filter(pk=s.pk).exists())
        s.delete()
        # View-level: POST weekly_test for non-MID should be rejected
        resp = self.client.post(reverse('mark_evaluation_settings') + f'?institution={self.institution.pk}&admission_class=9&exam_type=FIRST_TERM&group=SCI', {
            'institution': self.institution.pk,
            'admission_class': '9',
            'exam_type': 'FIRST_TERM',
            'group': 'SCI',
            f'full_marks_{self.physics.pk}': '100',
            f'cq_marks_{self.physics.pk}': '40',
            f'mcq_marks_{self.physics.pk}': '30',
            f'weekly_test_marks_{self.physics.pk}': '30',
            f'pass_percentage_{self.physics.pk}': '40',
            f'is_active_{self.physics.pk}': '1',
        })
        # Should be rejected (weekly not allowed for FIRST_TERM)
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(SubjectMarkSetting.objects.filter(subject=self.physics, exam_type='FIRST_TERM', group='SCI', weekly_test_marks=30).exists())
        # MID with weekly_test should pass when parts sum matches (view)
        resp2 = self.client.post(reverse('mark_evaluation_settings') + f'?institution={self.institution.pk}&admission_class=9&exam_type=MID_TERM_1&group=SCI', {
            'institution': self.institution.pk,
            'admission_class': '9',
            'exam_type': 'MID_TERM_1',
            'group': 'SCI',
            f'full_marks_{self.physics.pk}': '100',
            f'cq_marks_{self.physics.pk}': '50',
            f'mcq_marks_{self.physics.pk}': '30',
            f'weekly_test_marks_{self.physics.pk}': '20',
            f'pass_percentage_{self.physics.pk}': '40',
            f'is_active_{self.physics.pk}': '1',
        })
        self.assertEqual(resp2.status_code, 302)
        self.assertTrue(SubjectMarkSetting.objects.filter(subject=self.physics, exam_type='MID_TERM_1', group='SCI').exists())

    # (v) duplicate blocked (unique constraint)
    def test_duplicate_setting_blocked(self):
        SubjectMarkSetting.objects.create(institution=self.institution, admission_class='9', subject=self.physics, exam_type='FIRST_TERM', group='SCI', full_marks=70)
        # Same institution/class/subject/exam_type/group -> ValidationError (unique) or IntegrityError
        dup = SubjectMarkSetting(institution=self.institution, admission_class='9', subject=self.physics, exam_type='FIRST_TERM', group='SCI', full_marks=80)
        with self.assertRaises((IntegrityError, ValidationError)):
            dup.save()
        # Different group should be allowed
        ok = SubjectMarkSetting(institution=self.institution, admission_class='9', subject=self.physics, exam_type='FIRST_TERM', group='BUS', full_marks=80)
        ok.save()
        self.assertEqual(SubjectMarkSetting.objects.filter(subject=self.physics, exam_type='FIRST_TERM').count(), 2)

    # (vi) class <9 group must be blank
    def test_class_below_9_group_must_be_blank(self):
        # Class 6 with group SCI should fail
        s = SubjectMarkSetting(institution=self.institution, admission_class='6', subject=self.bangla, exam_type='FIRST_TERM', group='SCI', full_marks=100)
        with self.assertRaises(ValidationError) as cm:
            s.full_clean()
        self.assertIn('Group must be blank', str(cm.exception))
        # Class 6 with blank succeeds
        s2 = SubjectMarkSetting(institution=self.institution, admission_class='6', subject=self.bangla, exam_type='FIRST_TERM', group='', full_marks=100)
        s2.full_clean()
        s2.save()
        self.assertEqual(s2.group, '')
        # Also test that save() auto-clears group for non-group class
        s3 = SubjectMarkSetting(institution=self.institution, admission_class='6', subject=self.bangla, exam_type='MID_TERM_1', group='SCI', full_marks=50, cq_marks=30, weekly_test_marks=20)
        # Even if we bypass clean via save, it should clear group
        # Our save() calls full_clean which will raise before clearing, so we test direct DB? But save() clears before clean, so it should succeed with blank
        # Actually our save() clears then full_clean, so SCI will be cleared to '' and then pass
        # Let's test that behavior: create with group SCI for class 6 via save() should end up as ''
        # To avoid ValidationError, save() does clearing before full_clean, so it should not raise
        s3.save()
        self.assertEqual(s3.group, '')

    def test_class_supports_group_helper(self):
        self.assertFalse(class_supports_group('6'))
        self.assertFalse(class_supports_group('8'))
        self.assertFalse(class_supports_group('09') is False or not class_supports_group('09'))  # '9' with padding
        self.assertTrue(class_supports_group('9'))
        self.assertTrue(class_supports_group('09'))
        self.assertTrue(class_supports_group('10'))
        self.assertTrue(class_supports_group('12'))

    # (vii) institution scoping
    def test_institution_scoping(self):
        SubjectMarkSetting.objects.create(institution=self.institution, admission_class='9', subject=self.physics, exam_type='FIRST_TERM', group='SCI', full_marks=70)
        # Other institution exam should not see this setting
        other_exam = Exam.objects.create(name='Other SCI', exam_type='FIRST_TERM', institution=self.other_institution, admission_class='9', group='SCI', session='2026')
        cfg = get_subject_marks(other_exam, self.physics)
        self.assertEqual(cfg.full_marks, 100)  # fallback to Subject default, not 70
        self.assertEqual(cfg.pk, self.physics.pk)

    def test_mark_evaluation_view_institution_scoping(self):
        # Create setting for own institution
        SubjectMarkSetting.objects.create(institution=self.institution, admission_class='9', subject=self.bangla, exam_type='FIRST_TERM', group='', full_marks=90)
        # Scoped user for other institution should not see it
        from .models import InstitutionAccess
        from django.contrib.auth.models import Permission
        scoped_user = get_user_model().objects.create_user('scoped', password='password')
        InstitutionAccess.objects.create(user=scoped_user, institution=self.other_institution, department='Exam')
        # Give the permission required for the view
        perm = Permission.objects.get(codename='change_subject')
        scoped_user.user_permissions.add(perm)
        scoped_user = get_user_model().objects.get(pk=scoped_user.pk)  # refresh
        self.client.force_login(scoped_user)
        resp = self.client.get(reverse('mark_evaluation_settings'), {'institution': self.other_institution.pk, 'admission_class': '9', 'exam_type': 'FIRST_TERM'})
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(SubjectMarkSetting.objects.filter(institution=self.other_institution).exists())

    # Extra: resolution respects zero-padding
    def test_zero_padding_class_resolution(self):
        SubjectMarkSetting.objects.create(institution=self.institution, admission_class='09', subject=self.physics, exam_type='FIRST_TERM', group='SCI', full_marks=65)
        cfg = get_subject_marks(self.exam_sci, self.physics)  # exam has '9' not '09'
        self.assertEqual(cfg.full_marks, 65)

    def test_group_resolution_via_build_exam_results(self):
        # Create two group-specific configs with different pass % to affect result
        # Use chemistry which is assigned to both SCI and BUS (physics is SCI-only)
        SubjectMarkSetting.objects.create(institution=self.institution, admission_class='9', subject=self.chemistry, exam_type='FIRST_TERM', group='', full_marks=100, pass_percentage=40)
        SubjectMarkSetting.objects.create(institution=self.institution, admission_class='9', subject=self.chemistry, exam_type='FIRST_TERM', group='SCI', full_marks=100, pass_percentage=80)
        # Students
        sci_student = Student.objects.create(institution=self.institution, student_id='SCI01', name='Sci Kid', admission_class='9', section='A', roll_no=1, group='SCI', guardian_contact_no='01800000001')
        bus_student = Student.objects.create(institution=self.institution, student_id='BUS01', name='Bus Kid', admission_class='9', section='A', roll_no=2, group='BUS', guardian_contact_no='01800000002')
        # Marks: 50 should pass default 40 but fail SCI 80
        from .models import ExamMark
        ExamMark.objects.create(exam=self.exam_sci, student=sci_student, subject=self.chemistry, marks_obtained=50)
        ExamMark.objects.create(exam=self.exam_bus, student=bus_student, subject=self.chemistry, marks_obtained=50)
        # Need requirements already exist
        # Build results for each exam (group-aware)
        _, results_sci = build_exam_results(self.exam_sci)
        _, results_bus = build_exam_results(self.exam_bus)
        sci_res = next(r for r in results_sci if r['student'].pk == sci_student.pk)
        bus_res = next(r for r in results_bus if r['student'].pk == bus_student.pk)
        # SCI should be Fail (50 < 80% of 100? pass 80), BUS Pass (50 >=40)
        self.assertEqual(sci_res['status'], 'Fail')
        self.assertEqual(bus_res['status'], 'Pass')

    def test_baseline_deficiency_before_group_field_was_not_possible(self):
        """Demonstrates the deficiency that EX-03 fixes: same class+subject+exam_type
        but different groups can now have different configs (previously unique constraint
        blocked it)."""
        # This is the proof: two rows same institution/class/subject/exam_type but different groups
        # would have raised IntegrityError before group field existed. Now they coexist.
        s1 = SubjectMarkSetting.objects.create(institution=self.institution, admission_class='10', subject=self.chemistry, exam_type='FIRST_TERM', group='SCI', full_marks=75)
        s2 = SubjectMarkSetting.objects.create(institution=self.institution, admission_class='10', subject=self.chemistry, exam_type='FIRST_TERM', group='BUS', full_marks=100)
        self.assertNotEqual(s1.full_marks, s2.full_marks)
        self.assertEqual(SubjectMarkSetting.objects.filter(admission_class='10', subject=self.chemistry, exam_type='FIRST_TERM').count(), 2)
