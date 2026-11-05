"""OF-08 — archive / promotion / certificate audit (prompt 16).

Flow matrix (happy / boundary / invalid / unauthorized / cross-institution):

Archive        delete_student + bulk archive, archived list, previous status kept
Restore        single + bulk, exact previous status, purged/active/GET refused
Purge          single + bulk, destroyed documents recorded in the audit trail
Promotion      class/section remap, source roll kept, batch + history, session
Promotion      second run in the same session blocked, allowed after rollback
Rollback       reverts only students still at target, twice refused, audited
Transfer cert. issue/print, second issue redirects, numbering, audit row
Certificate    issue/print/list, numbering per type, field errors rendered
ID card        identity fields + institution, scoped lookups
Numbering      year-wise sequence, no collision with hand-set numbers, no reuse
               after a purge (counter survives the deleted document row)

Owner decisions applied in this session (Arena chat, 2026-10-15):
  1. purge is allowed for TC/certificate holders, but warns loudly and records
     the destroyed document numbers in the audit trail (no block);
  2. numbers stay year-wise but must be collision-safe and never reused;
  3. a class/section may be promoted once per session — a second run is blocked,
     and becomes possible again after the batch is rolled back.

Every test uses synthetic data only.
"""
from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import (
    AuditLog, Certificate, Institution, InstitutionAccess, PromotionBatch,
    Student, StudentPromotionHistory, TransferCertificate,
)


def messages_of(response):
    return [str(m.message) for m in get_messages(response.wsgi_request)]


def grant(user, *codenames):
    for codename in codenames:
        user.user_permissions.add(Permission.objects.get(codename=codename))
    return user


class FlowFixtureMixin:
    """One school with two class-6 'A' students plus an outside institution."""

    def setUp(self):
        self.institution = Institution.objects.create(name='OF08 School', classes='6,7,8,9')
        self.other_institution = Institution.objects.create(name='OF08 Other', classes='6,9')
        self.admin = get_user_model().objects.create_superuser(
            username='of08-admin', password='password',
        )
        self.student = Student.objects.create(
            institution=self.institution, student_id='A001', name='Audit Student',
            admission_class='6', section='A', admission_year=2026, roll_no=1,
        )
        self.peer = Student.objects.create(
            institution=self.institution, student_id='A002', name='Peer Student',
            admission_class='6', section='A', admission_year=2026, roll_no=2,
        )
        self.outsider = Student.objects.create(
            institution=self.other_institution, student_id='B001', name='Other School Student',
            admission_class='9', section='A', admission_year=2026, roll_no=1,
        )
        self.client.force_login(self.admin)

    def archive(self, student):
        response = self.client.post(reverse('delete_student', args=[student.pk]))
        student.refresh_from_db()
        return response


class ArchiveLifecycleTests(FlowFixtureMixin, TestCase):
    def test_archive_keeps_the_row_and_records_actor_time_and_previous_status(self):
        self.student.status = 'TRANSFERRED'
        self.student.save(update_fields=['status'])
        self.archive(self.student)
        self.assertTrue(self.student.is_archived)
        self.assertEqual(self.student.status, 'DISCONTINUED')
        self.assertEqual(self.student.pre_archive_status, 'TRANSFERRED')
        self.assertIsNotNone(self.student.archived_at)
        self.assertEqual(self.student.archived_by, self.admin)
        audit = AuditLog.objects.get(action='student_archived', object_id=str(self.student.pk))
        self.assertEqual(audit.details.get('source'), 'delete_student')
        self.assertEqual(audit.snapshot.get('pre_archive_status'), 'TRANSFERRED')
        self.assertEqual(audit.institution, self.institution)
        self.assertTrue(Student.objects.filter(pk=self.student.pk).exists())

    def test_a_tc_holder_is_archived_like_any_other_student(self):
        tc = TransferCertificate.objects.create(student=self.student, reason='Family relocation')
        self.student.status = 'TRANSFERRED'
        self.student.save(update_fields=['status'])
        self.archive(self.student)
        self.assertTrue(self.student.is_archived)
        self.assertEqual(self.student.pre_archive_status, 'TRANSFERRED')
        # The TC survives archiving: only a purge destroys it.
        self.assertTrue(TransferCertificate.objects.filter(pk=tc.pk).exists())

    def test_archived_page_lists_archived_rows_only(self):
        self.archive(self.student)
        response = self.client.get(reverse('archived_students'))
        self.assertContains(response, 'Audit Student')
        self.assertNotContains(response, 'Peer Student')

    def test_restore_returns_the_exact_previous_status_and_is_audited(self):
        self.student.status = 'TRANSFERRED'
        self.student.save(update_fields=['status'])
        self.archive(self.student)
        response = self.client.post(reverse('restore_student', args=[self.student.pk]))
        self.assertEqual(response.status_code, 302)
        self.student.refresh_from_db()
        self.assertFalse(self.student.is_archived)
        self.assertEqual(self.student.status, 'TRANSFERRED')
        self.assertEqual(self.student.pre_archive_status, '')
        self.assertEqual(self.student.restored_by, self.admin)
        audit = AuditLog.objects.get(action='student_restored', object_id=str(self.student.pk))
        self.assertEqual(audit.details.get('source'), 'restore_student')

    def test_discontinued_student_restores_to_discontinued_not_active(self):
        self.client.post(reverse('discontinue_student', args=[self.student.pk]), {'reason': 'Left'})
        self.student.refresh_from_db()
        self.assertEqual(self.student.status, 'DISCONTINUED')
        self.assertFalse(self.student.is_archived)
        self.archive(self.student)
        self.client.post(reverse('restore_student', args=[self.student.pk]))
        self.student.refresh_from_db()
        self.assertEqual(self.student.status, 'DISCONTINUED')
        self.assertFalse(self.student.is_archived)

    def test_restore_refuses_a_student_that_is_not_archived(self):
        response = self.client.post(reverse('restore_student', args=[self.student.pk]))
        self.assertEqual(response.status_code, 404)
        self.student.refresh_from_db()
        self.assertFalse(self.student.is_archived)

    def test_restore_of_a_purged_student_is_404(self):
        self.archive(self.student)
        pk = self.student.pk
        self.client.post(reverse('purge_archived_student', args=[pk]))
        response = self.client.post(reverse('restore_student', args=[pk]))
        self.assertEqual(response.status_code, 404)

    def test_restore_and_purge_are_post_only(self):
        self.archive(self.student)
        self.assertEqual(
            self.client.get(reverse('restore_student', args=[self.student.pk])).status_code, 405,
        )
        self.assertEqual(
            self.client.get(reverse('purge_archived_student', args=[self.student.pk])).status_code, 405,
        )
        self.assertTrue(Student.objects.filter(pk=self.student.pk).exists())

    def test_purge_of_a_purged_student_is_404(self):
        self.archive(self.student)
        pk = self.student.pk
        self.client.post(reverse('purge_archived_student', args=[pk]))
        response = self.client.post(reverse('purge_archived_student', args=[pk]))
        self.assertEqual(response.status_code, 404)

    def test_bulk_flows_reject_an_empty_selection(self):
        restore = self.client.post(reverse('bulk_restore_students'), {})
        self.assertEqual(restore.status_code, 302)
        self.assertIn('No students were selected.', messages_of(restore))
        purge = self.client.post(reverse('bulk_purge_archived_students'), {})
        self.assertEqual(purge.status_code, 302)
        self.assertIn('No students were selected.', messages_of(purge))

    def test_bulk_restore_restores_every_selected_student(self):
        self.archive(self.student)
        self.archive(self.peer)
        response = self.client.post(reverse('bulk_restore_students'), {
            'student_ids': [self.student.pk, self.peer.pk],
        })
        self.assertEqual(response.status_code, 302)
        for student in (self.student, self.peer):
            student.refresh_from_db()
            self.assertFalse(student.is_archived)
            self.assertEqual(student.status, 'ACTIVE')

    def test_archive_restore_and_purge_need_their_permissions(self):
        plain = get_user_model().objects.create_user(username='of08-plain', password='password')
        self.client.force_login(plain)
        self.assertEqual(self.client.get(reverse('archived_students')).status_code, 403)
        self.assertEqual(
            self.client.post(reverse('delete_student', args=[self.student.pk])).status_code, 403,
        )
        self.assertEqual(
            self.client.post(reverse('restore_student', args=[self.student.pk])).status_code, 403,
        )
        self.assertEqual(
            self.client.post(reverse('purge_archived_student', args=[self.student.pk])).status_code, 403,
        )
        self.assertTrue(Student.objects.filter(pk=self.student.pk).exists())

    def test_scoped_clerk_cannot_restore_or_purge_another_institution(self):
        self.archive(self.outsider)
        clerk = grant(
            get_user_model().objects.create_user(username='of08-clerk', password='password'),
            'view_student', 'delete_student',
        )
        InstitutionAccess.objects.create(user=clerk, institution=self.institution, department='Office')
        self.client.force_login(clerk)
        self.assertEqual(
            self.client.post(reverse('restore_student', args=[self.outsider.pk])).status_code, 404,
        )
        self.assertEqual(
            self.client.post(reverse('purge_archived_student', args=[self.outsider.pk])).status_code, 404,
        )
        self.outsider.refresh_from_db()
        self.assertTrue(self.outsider.is_archived)
        self.assertTrue(Student.objects.filter(pk=self.outsider.pk).exists())


class PurgeDocumentWarningTests(FlowFixtureMixin, TestCase):
    """Owner decision 1 — purge stays allowed, but never silently destroys a
    TC or certificates: the clerk is warned and the audit row keeps the
    destroyed document numbers."""

    def test_purging_a_tc_holder_records_the_destroyed_certificate(self):
        tc = TransferCertificate.objects.create(student=self.student, reason='Family relocation')
        self.archive(self.student)
        response = self.client.post(reverse('purge_archived_student', args=[self.student.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Student.objects.filter(pk=self.student.pk).exists())
        self.assertFalse(TransferCertificate.objects.filter(pk=tc.pk).exists())
        audit = AuditLog.objects.get(action='student_purged', object_id=str(self.student.pk))
        self.assertEqual(audit.details['destroyed_documents']['transfer_certificate'], tc.tc_number)
        self.assertIn(tc.tc_number, messages_of(response)[-1])

    def test_purging_a_certificate_holder_lists_every_destroyed_number(self):
        numbers = [
            Certificate.objects.create(student=self.student, certificate_type=kind).certificate_number
            for kind in ('CHARACTER', 'STUDY')
        ]
        self.archive(self.student)
        response = self.client.post(reverse('purge_archived_student', args=[self.student.pk]))
        audit = AuditLog.objects.get(action='student_purged', object_id=str(self.student.pk))
        self.assertEqual(audit.details['destroyed_documents']['certificates'], numbers)
        warning = messages_of(response)[-1]
        for number in numbers:
            self.assertIn(number, warning)

    def test_purge_without_documents_has_no_document_warning(self):
        self.archive(self.student)
        response = self.client.post(reverse('purge_archived_student', args=[self.student.pk]))
        audit = AuditLog.objects.get(action='student_purged', object_id=str(self.student.pk))
        self.assertEqual(audit.details['destroyed_documents'], {})
        self.assertNotIn('certificate', messages_of(response)[-1].lower())
        self.assertNotIn('transfer', messages_of(response)[-1].lower())

    def test_bulk_purge_writes_one_audit_row_per_destroyed_document_set(self):
        tc = TransferCertificate.objects.create(student=self.student)
        self.archive(self.student)
        self.archive(self.peer)
        response = self.client.post(reverse('bulk_purge_archived_students'), {
            'student_ids': [self.student.pk, self.peer.pk],
        })
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Student.objects.filter(pk__in=[self.student.pk, self.peer.pk]).exists())
        with_documents = AuditLog.objects.get(action='student_purged', object_id=str(self.student.pk))
        without = AuditLog.objects.get(action='student_purged', object_id=str(self.peer.pk))
        self.assertEqual(
            with_documents.details['destroyed_documents']['transfer_certificate'], tc.tc_number,
        )
        self.assertEqual(without.details['destroyed_documents'], {})

    def test_archived_page_warns_that_documents_die_with_the_row(self):
        TransferCertificate.objects.create(student=self.student)
        self.archive(self.student)
        response = self.client.get(reverse('archived_students'))
        self.assertContains(response, 'Transfer Certificate')

    def test_archived_page_names_the_tc_in_the_single_row_confirmation(self):
        tc = TransferCertificate.objects.create(student=self.student)
        self.archive(self.student)
        response = self.client.get(reverse('archived_students'))
        content = response.content.decode()
        self.assertIn('PERMANENTLY delete', content)
        self.assertIn(tc.tc_number, content)

    def test_purging_one_student_leaves_other_documents_untouched(self):
        tc = TransferCertificate.objects.create(student=self.peer)
        self.archive(self.student)
        self.client.post(reverse('purge_archived_student', args=[self.student.pk]))
        self.assertTrue(TransferCertificate.objects.filter(pk=tc.pk).exists())
        self.assertTrue(Student.objects.filter(pk=self.peer.pk).exists())


class PromotionFlowTests(FlowFixtureMixin, TestCase):
    SESSION = '2026-2027'

    def promote(self, **overrides):
        data = {
            'from_class': '6', 'from_section': 'A', 'to_class': '7',
            'to_section': 'B', 'session': self.SESSION,
        }
        data.update(overrides)
        return self.client.post(reverse('student_promotion'), data)

    def test_promotion_remaps_class_section_and_keeps_the_source_roll(self):
        response = self.promote()
        self.assertEqual(response.status_code, 302)
        self.student.refresh_from_db()
        self.peer.refresh_from_db()
        self.assertEqual((self.student.admission_class, self.student.section), ('7', 'B'))
        self.assertEqual((self.peer.admission_class, self.peer.section), ('7', 'B'))
        # Migration 0021 keeps the roll the student held before the move.
        self.assertEqual(self.student.roll_no, 1)
        batch = PromotionBatch.objects.get()
        self.assertEqual(batch.institution, self.institution)
        self.assertEqual(batch.actor, self.admin)
        history = StudentPromotionHistory.objects.get(batch=batch, student=self.student)
        self.assertEqual(
            (history.source_class, history.source_section, history.source_roll_no),
            ('6', 'A', 1),
        )
        self.assertEqual((history.target_class, history.target_section), ('7', 'B'))
        self.assertTrue(AuditLog.objects.filter(action='students_promoted').exists())

    def test_promotion_leaves_other_sections_and_archived_students_alone(self):
        other_section = Student.objects.create(
            institution=self.institution, student_id='A003', name='Section B Student',
            admission_class='6', section='B', admission_year=2026,
        )
        self.archive(self.peer)
        self.promote()
        self.student.refresh_from_db()
        other_section.refresh_from_db()
        self.peer.refresh_from_db()
        self.assertEqual(self.student.admission_class, '7')
        self.assertEqual(other_section.admission_class, '6')
        self.assertEqual(self.peer.admission_class, '6')
        self.assertTrue(self.peer.is_archived)

    def test_promotion_requires_a_session(self):
        response = self.promote(session='  ')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(PromotionBatch.objects.count(), 0)

    def test_promotion_for_an_empty_class_creates_no_batch(self):
        response = self.promote(from_class='11', to_class='12')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(PromotionBatch.objects.count(), 0)
        self.assertIn('No students found for the selected class/section.', messages_of(response))

    def test_second_run_in_the_same_session_is_blocked(self):
        self.promote()
        late = Student.objects.create(
            institution=self.institution, student_id='A004', name='Late Arrival',
            admission_class='6', section='A', admission_year=2026,
        )
        response = self.promote(to_class='8', to_section='A')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(PromotionBatch.objects.count(), 1)
        late.refresh_from_db()
        self.assertEqual(late.admission_class, '6')
        self.assertIn('already been promoted', ' '.join(messages_of(response) + [
            str(e) for e in response.context['form'].non_field_errors()
        ]))

    def test_blocked_second_run_with_class_spelling_variant_is_still_blocked(self):
        self.promote(from_class='6')
        Student.objects.create(
            institution=self.institution, student_id='A005', name='Spelling Variant',
            admission_class='06', section='A', admission_year=2026,
        )
        response = self.promote(from_class='06')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(PromotionBatch.objects.count(), 1)

    def test_promotion_is_allowed_again_after_the_batch_is_rolled_back(self):
        self.promote()
        batch = PromotionBatch.objects.get()
        self.client.post(reverse('rollback_student_promotion', args=[batch.pk]))
        self.student.refresh_from_db()
        self.assertEqual(self.student.admission_class, '6')
        response = self.promote(to_class='8', to_section='A')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(PromotionBatch.objects.count(), 2)
        self.student.refresh_from_db()
        self.assertEqual(self.student.admission_class, '8')

    def test_another_session_may_promote_the_same_class(self):
        self.promote()
        Student.objects.create(
            institution=self.institution, student_id='A006', name='Next Session',
            admission_class='6', section='A', admission_year=2026,
        )
        response = self.promote(session='2027-2028')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(PromotionBatch.objects.count(), 2)

    def test_another_section_may_be_promoted_in_the_same_session(self):
        section_b = Student.objects.create(
            institution=self.institution, student_id='A007', name='Section B Student',
            admission_class='6', section='B', admission_year=2026,
        )
        self.promote(from_section='A')
        response = self.promote(from_section='B')
        self.assertEqual(response.status_code, 302)
        section_b.refresh_from_db()
        self.assertEqual(section_b.admission_class, '7')
        self.assertEqual(PromotionBatch.objects.count(), 2)

    def test_rollback_restores_only_students_still_at_the_target(self):
        self.promote()
        self.student.admission_class = '8'
        self.student.save(update_fields=['admission_class'])
        batch = PromotionBatch.objects.get()
        response = self.client.post(reverse('rollback_student_promotion', args=[batch.pk]))
        self.assertEqual(response.status_code, 302)
        self.student.refresh_from_db()
        self.peer.refresh_from_db()
        batch.refresh_from_db()
        self.assertEqual(self.student.admission_class, '8')
        self.assertEqual((self.peer.admission_class, self.peer.section), ('6', 'A'))
        self.assertEqual(self.peer.roll_no, 2)
        self.assertIsNotNone(batch.rolled_back_at)
        self.assertEqual(batch.rollback_actor, self.admin)
        self.assertEqual(batch.student_history.filter(rolled_back_at__isnull=False).count(), 1)
        self.assertTrue(AuditLog.objects.filter(action='students_promotion_rollback').exists())

    def test_rollback_twice_is_refused_and_keeps_the_first_rollback(self):
        self.promote()
        batch = PromotionBatch.objects.get()
        self.client.post(reverse('rollback_student_promotion', args=[batch.pk]))
        batch.refresh_from_db()
        first = batch.rolled_back_at
        response = self.client.post(reverse('rollback_student_promotion', args=[batch.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn('already been rolled back', ' '.join(messages_of(response)))
        batch.refresh_from_db()
        self.assertEqual(batch.rolled_back_at, first)
        self.assertEqual(AuditLog.objects.filter(action='students_promotion_rollback').count(), 1)

    def test_rollback_by_a_scoped_clerk_cannot_touch_another_institution(self):
        self.promote(from_class='9', from_section='A', to_class='10', to_section='A')
        batch = PromotionBatch.objects.get()
        clerk = grant(
            get_user_model().objects.create_user(username='of08-promoter', password='password'),
            'view_student', 'change_student', 'view_promotionbatch',
        )
        InstitutionAccess.objects.create(user=clerk, institution=self.institution, department='Office')
        self.client.force_login(clerk)
        response = self.client.post(reverse('rollback_student_promotion', args=[batch.pk]))
        self.assertEqual(response.status_code, 404)
        self.outsider.refresh_from_db()
        self.assertEqual(self.outsider.admission_class, '10')

    def test_promotion_history_needs_the_permission_and_the_office_department(self):
        plain = get_user_model().objects.create_user(username='of08-history', password='password')
        self.client.force_login(plain)
        self.assertEqual(self.client.get(reverse('student_promotion_history')).status_code, 403)
        grant(plain, 'view_student', 'view_promotionbatch')
        session = self.client.session
        session['selected_department'] = 'Accounts'
        session.save()
        response = self.client.get(reverse('student_promotion_history'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('dashboard'))


class CertificateDocumentTests(FlowFixtureMixin, TestCase):
    def test_issuing_a_tc_sets_status_transferred_and_is_audited(self):
        response = self.client.post(reverse('issue_tc', args=[self.student.pk]), {
            'reason': 'Family relocation', 'remarks': 'No dues', 'issued_by': 'Principal',
        })
        self.assertEqual(response.status_code, 302)
        tc = TransferCertificate.objects.get(student=self.student)
        self.assertEqual(tc.tc_number, f'TC-{timezone.now().year}-001')
        self.student.refresh_from_db()
        self.assertEqual(self.student.status, 'TRANSFERRED')
        audit = AuditLog.objects.get(action='transfer_certificate_issued')
        self.assertEqual(audit.object_id, str(tc.pk))
        self.assertEqual(audit.institution, self.institution)
        self.assertEqual(audit.snapshot.get('tc_number'), tc.tc_number)

    def test_second_tc_issue_redirects_to_the_existing_certificate(self):
        self.client.post(reverse('issue_tc', args=[self.student.pk]), {'reason': 'First'})
        tc = TransferCertificate.objects.get(student=self.student)
        response = self.client.post(reverse('issue_tc', args=[self.student.pk]), {'reason': 'Second'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('view_tc', args=[tc.pk]))
        self.assertEqual(TransferCertificate.objects.filter(student=self.student).count(), 1)

    def test_tc_print_renders_every_field(self):
        self.client.post(reverse('issue_tc', args=[self.student.pk]), {
            'reason': 'Family relocation', 'remarks': 'Dues cleared', 'issued_by': 'Head Master',
        })
        tc = TransferCertificate.objects.get(student=self.student)
        response = self.client.get(reverse('view_tc', args=[tc.pk]))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        for value in (tc.tc_number, 'Audit Student', 'A001', 'Family relocation', 'Dues cleared', 'Head Master'):
            self.assertIn(value, content)

    def test_tc_print_of_a_certificate_holder_uses_the_transferred_student(self):
        self.client.post(reverse('issue_tc', args=[self.student.pk]), {'reason': 'Relocation'})
        tc = TransferCertificate.objects.get(student=self.student)
        response = self.client.get(reverse('view_tc', args=[tc.pk]))
        self.assertContains(response, 'Transfer Certificate')

    def test_issuing_a_certificate_is_audited_and_printable(self):
        response = self.client.post(reverse('issue_certificate', args=[self.student.pk]), {
            'certificate_type': 'STUDY', 'purpose': 'Bank account', 'issued_by': 'Principal',
        })
        self.assertEqual(response.status_code, 302)
        certificate = Certificate.objects.get(student=self.student)
        self.assertEqual(certificate.certificate_number, f'STU-{timezone.now().year}-001')
        audit = AuditLog.objects.get(action='certificate_issued')
        self.assertEqual(audit.object_id, str(certificate.pk))
        self.assertEqual(audit.institution, self.institution)
        response = self.client.get(reverse('view_certificate', args=[certificate.pk]))
        content = response.content.decode()
        for value in (certificate.certificate_number, 'Audit Student', 'A001',
                      'Study Certificate', 'Bank account', 'Principal'):
            self.assertIn(value, content)

    def test_certificate_list_shows_only_this_students_certificates(self):
        mine = Certificate.objects.create(student=self.student, certificate_type='CHARACTER')
        Certificate.objects.create(student=self.peer, certificate_type='BONAFIDE')
        response = self.client.get(reverse('certificate_list', args=[self.student.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, mine.certificate_number)
        self.assertNotContains(response, 'BON-')

    def test_certificate_issue_without_a_type_shows_a_field_error(self):
        response = self.client.post(reverse('issue_certificate', args=[self.student.pk]), {
            'certificate_type': '', 'purpose': 'Bank account',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'This field is required.')
        self.assertEqual(Certificate.objects.count(), 0)

    def test_document_issue_requires_its_permission(self):
        plain = get_user_model().objects.create_user(username='of08-docs', password='password')
        self.client.force_login(plain)
        self.assertEqual(
            self.client.post(reverse('issue_tc', args=[self.student.pk]), {'reason': 'x'}).status_code, 403,
        )
        self.assertEqual(
            self.client.post(
                reverse('issue_certificate', args=[self.student.pk]), {'certificate_type': 'STUDY'},
            ).status_code, 403,
        )
        self.assertEqual(TransferCertificate.objects.count(), 0)
        self.assertEqual(Certificate.objects.count(), 0)

    def test_scoped_clerk_cannot_issue_documents_for_another_institution(self):
        clerk = grant(
            get_user_model().objects.create_user(username='of08-doc-clerk', password='password'),
            'view_student', 'add_transfercertificate', 'add_certificate',
        )
        InstitutionAccess.objects.create(user=clerk, institution=self.institution, department='Office')
        self.client.force_login(clerk)
        self.assertEqual(
            self.client.post(reverse('issue_tc', args=[self.outsider.pk]), {'reason': 'x'}).status_code, 404,
        )
        self.assertEqual(
            self.client.post(
                reverse('issue_certificate', args=[self.outsider.pk]), {'certificate_type': 'STUDY'},
            ).status_code, 404,
        )

    def test_document_reads_404_for_unknown_and_other_institution_rows(self):
        tc = TransferCertificate.objects.create(student=self.outsider)
        certificate = Certificate.objects.create(student=self.outsider, certificate_type='STUDY')
        clerk = grant(
            get_user_model().objects.create_user(username='of08-reader', password='password'),
            'view_student',
        )
        InstitutionAccess.objects.create(user=clerk, institution=self.institution, department='Office')
        self.client.force_login(clerk)
        for url in (
            reverse('view_tc', args=[tc.pk]),
            reverse('view_certificate', args=[certificate.pk]),
            reverse('student_id_card', args=[self.outsider.pk]),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)
        # Same surface, unknown pk.
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('view_tc', args=[99999])).status_code, 404)
        self.assertEqual(self.client.get(reverse('view_certificate', args=[99999])).status_code, 404)

    def test_id_card_renders_identity_fields_and_institution(self):
        response = self.client.get(reverse('student_id_card', args=[self.student.pk]))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        for value in ('Audit Student', 'A001', 'OF08 School', '6', '2026'):
            self.assertIn(value, content)

    def test_certificate_is_issued_for_an_archived_student_and_stays_scoped(self):
        """Audit finding: certificate issue has no status/class guard — a leaver
        still on record can request a certificate. Behaviour is pinned here so
        the owner can decide whether to restrict it later."""
        self.archive(self.student)
        response = self.client.post(reverse('issue_certificate', args=[self.student.pk]), {
            'certificate_type': 'CHARACTER', 'purpose': 'Left the school',
        })
        self.assertEqual(response.status_code, 302)
        certificate = Certificate.objects.get(student=self.student)
        self.assertTrue(self.student.is_archived)
        page = self.client.get(reverse('certificate_list', args=[self.student.pk]))
        self.assertContains(page, certificate.certificate_number)


class DocumentNumberingTests(FlowFixtureMixin, TestCase):
    """Owner decision 2 — keep the year-wise `TC-<year>-NNN` /
    `<TYPE>-<year>-NNN` shape, but make it collision-safe and never reuse a
    number once it has been printed, even if the row is later purged."""

    def issue_tc(self, student):
        self.client.post(reverse('issue_tc', args=[student.pk]), {'reason': 'Audit'})
        return TransferCertificate.objects.get(student=student)

    def test_tc_numbers_increment_within_the_year(self):
        first = self.issue_tc(self.student)
        second = self.issue_tc(self.peer)
        year = timezone.now().year
        self.assertEqual(first.tc_number, f'TC-{year}-001')
        self.assertEqual(second.tc_number, f'TC-{year}-002')

    def test_certificate_numbers_increment_per_type(self):
        year = timezone.now().year
        first = Certificate.objects.create(student=self.student, certificate_type='STUDY')
        second = Certificate.objects.create(student=self.peer, certificate_type='STUDY')
        bonafide = Certificate.objects.create(student=self.student, certificate_type='BONAFIDE')
        self.assertEqual(first.certificate_number, f'STU-{year}-001')
        self.assertEqual(second.certificate_number, f'STU-{year}-002')
        self.assertEqual(bonafide.certificate_number, f'BON-{year}-001')

    def test_a_hand_typed_number_is_not_handed_out_a_second_time(self):
        TransferCertificate.objects.create(student=self.peer, tc_number=f'TC-{timezone.now().year}-002')
        tc = self.issue_tc(self.student)
        self.assertEqual(tc.tc_number, f'TC-{timezone.now().year}-003')
        self.assertEqual(TransferCertificate.objects.filter(tc_number=tc.tc_number).count(), 1)

    def test_purged_tc_number_is_never_reissued(self):
        first = self.issue_tc(self.student)
        self.archive(self.student)
        self.client.post(reverse('purge_archived_student', args=[self.student.pk]))
        self.assertFalse(TransferCertificate.objects.filter(pk=first.pk).exists())
        second = self.issue_tc(self.peer)
        self.assertNotEqual(second.tc_number, first.tc_number)
        self.assertEqual(second.tc_number, f'TC-{timezone.now().year}-002')

    def test_purged_certificate_number_is_never_reissued(self):
        first = Certificate.objects.create(student=self.student, certificate_type='STUDY')
        self.archive(self.student)
        self.client.post(reverse('purge_archived_student', args=[self.student.pk]))
        second = Certificate.objects.create(student=self.peer, certificate_type='STUDY')
        self.assertNotEqual(second.certificate_number, first.certificate_number)

    def test_last_years_numbers_do_not_leak_into_this_year(self):
        year = timezone.now().year
        last_year = TransferCertificate.objects.create(
            student=self.student, tc_number=f'TC-{year - 1}-001',
        )
        TransferCertificate.objects.filter(pk=last_year.pk).update(
            issue_date=date(year - 1, 6, 1),
        )
        tc = self.issue_tc(self.peer)
        self.assertEqual(tc.tc_number, f'TC-{year}-001')
        self.assertNotEqual(tc.tc_number, last_year.tc_number)
