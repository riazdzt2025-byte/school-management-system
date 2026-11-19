"""Mark correction workflow: draft → teacher check → exam-department decision.

The exam department owns the printed result, so a mark is never edited straight
from the register:

* the office files a request (``DRAFT``) with the corrected numbers and a reason;
* the subject teacher checks the numbers on the printed sheet and submits it
  (``SUBMITTED``) — after that the numbers are frozen, because a signed sheet
  cannot silently change;
* the exam department approves (``APPROVED``, the mark is written in the same
  transaction) or rejects it with a reason (``REJECTED``).

A requested mark lives on the request only. Nothing in ``result_utils`` reads
this table, so until an approval happens the result sheet, the register, the
rank list and the report cards are all unchanged — that is the owner's rule
("মূল রেজাল্টে কোনোভাবেই দেখা যাবে না").
"""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .audit import record_audit
from .models import ExamMark, MarkCorrectionRequest, MARK_PARTS


# The part columns, keyed the way the request stores them, in table order.
PART_FIELDS = {part['key']: part['obtained_field'] for part in MARK_PARTS}


def current_mark_snapshot(exam, student, subject):
    """``(total, parts)`` of the mark in the register right now.

    ``parts`` only holds the parts that carry a value: ``None`` means "nothing
    entered" (the student did not sit that paper), which is deliberately not the
    same as ``0`` and must survive a correction untouched.
    """
    mark = ExamMark.objects.filter(exam=exam, student=student, subject=subject).first()
    if mark is None:
        return None, {}
    parts = {
        key: getattr(mark, field)
        for key, field in PART_FIELDS.items()
        if getattr(mark, field) is not None
    }
    return mark.marks_obtained, parts


def snapshot_as_json(parts):
    """JSONField cannot store ``Decimal`` — store strings and read them back."""
    return {key: str(value) for key, value in parts.items() if value is not None}


def parts_from_json(data):
    values = {}
    for key, value in (data or {}).items():
        if key not in PART_FIELDS or value in (None, ''):
            continue
        try:
            values[key] = Decimal(str(value))
        except (ArithmeticError, ValueError, TypeError):
            continue
    return values


def apply_approved_mark(request_row):
    """Write the approved numbers into the register.

    Called inside the approval transaction. Refuses when somebody already
    changed the mark since the request was filed: the printed sheet shows the
    old number, so approving on top of a newer one would sign off a change
    nobody checked.
    """
    exam = request_row.exam
    student = request_row.student
    subject = request_row.subject

    stored_total, stored_parts = current_mark_snapshot(exam, student, subject)
    if _decimal(stored_total) != _decimal(request_row.current_total):
        raise ValidationError(
            'This mark was changed after the application was filed (it is '
            f'{stored_total if stored_total is not None else "empty"} now, the '
            f'application says {request_row.current_total}). File a fresh '
            'application for the current number.'
        )
    if snapshot_as_json(stored_parts) != snapshot_as_json(
        parts_from_json(request_row.current_parts)
    ):
        raise ValidationError(
            'The part marks were changed after the application was filed. File '
            'a fresh application for the current numbers.'
        )

    parts = parts_from_json(request_row.requested_parts)
    total = request_row.requested_total
    if total is None:
        raise ValidationError('The application has no requested mark to apply.')

    defaults = {'marks_obtained': total}
    # Every part column is written: an approved application decides the whole
    # row, so a part that was cleared must not keep its old value.
    for key, field in PART_FIELDS.items():
        defaults[field] = parts.get(key)
    ExamMark.objects.update_or_create(
        exam=exam, student=student, subject=subject, defaults=defaults,
    )


def _decimal(value):
    if value is None or value == '':
        return None
    return Decimal(str(value)).quantize(Decimal('0.01'))


def record_decision(request_row, *, actor, approve, reason='', teacher_note=''):
    """Move one request forward, writing everything the decision implies.

    Returns ``(ok, message)``. The caller decides how to show the message; the
    transaction is this function's business so a half-applied approval (mark
    written, request still SUBMITTED) is impossible.
    """
    if not request_row.is_open and not approve:
        return False, 'This application has already been decided.'
    now = timezone.now()
    with transaction.atomic():
        row = MarkCorrectionRequest.objects.select_for_update().get(pk=request_row.pk)
        if approve:
            if not row.can_be_approved:
                return False, 'This application has already been decided.'
            try:
                apply_approved_mark(row)
            except ValidationError as error:
                return False, '; '.join(error.messages)
            row.status = 'APPROVED'
            row.decided_by = actor
            row.decided_at = now
            row.decision_reason = reason.strip()
            row.save(update_fields=[
                'status', 'decided_by', 'decided_at', 'decision_reason', 'updated_at',
            ])
            record_audit(
                actor, 'mark_correction_approved', row,
                details={
                    'student': row.student.name,
                    'subject': row.subject.name,
                    'exam': row.exam.name,
                    'from': str(row.current_total),
                    'to': str(row.requested_total),
                    'reason': reason.strip(),
                },
            )
            return True, (
                f'Approved — {row.subject.name} for {row.student.name} is now '
                f'{row.requested_total}. Reprint any result sheet already issued.'
            )

        if not reason.strip():
            return False, 'Give a reason when rejecting an application.'
        row.status = 'REJECTED'
        row.decided_by = actor
        row.decided_at = now
        row.decision_reason = reason.strip()
        row.save(update_fields=[
            'status', 'decided_by', 'decided_at', 'decision_reason', 'updated_at',
        ])
        record_audit(
            actor, 'mark_correction_rejected', row,
            details={
                'student': row.student.name,
                'subject': row.subject.name,
                'requested': str(row.requested_total),
                'reason': reason.strip(),
            },
        )
        return True, f'Rejected — {row.student.name} keeps {row.current_total}.'
