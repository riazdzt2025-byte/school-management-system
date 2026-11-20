"""What a signed-in teacher may see: only their own classes.

A teacher logs in with the *Teacher* department and is linked to one
``Employee`` row (``Employee.user``). Everything below answers "which students
and subjects may this person touch", and every teacher-facing view asks these
functions instead of trusting a posted id.

The scope is the teacher's own ``TeacherAssignment`` rows for the running
session:

* a row with a **section** covers that section only;
* a row **without** a section covers the whole class (that is how the assign
  screen stores "all sections"), which is why the check is a pair of
  ``(class, section-or-blank)`` conditions rather than a plain class filter.

Nothing here grants approval rights: approving a correction belongs to the Exam
department, and this module never widens it.
"""
from .models import (
    Employee, Exam, MarkCorrectionRequest, Student, Subject, TeacherAssignment,
    current_academic_session,
)
from .result_utils import class_filter_variants


def teacher_employee(user):
    """The ``Employee`` row behind this login, or ``None``.

    Only an *active* teaching employee is returned: a resigned teacher keeps
    their account but loses the scope, so their screens come up empty rather
    than showing the class they used to take.
    """
    if user is None or not getattr(user, 'is_authenticated', False):
        return None
    employee = getattr(user, 'employee_profile', None)
    if employee is None or employee.status != 'ACTIVE':
        return None
    return employee


def is_teacher_account(user):
    """True when this login is a teacher (not an office clerk or admin).

    An admin who is also linked to an employee row keeps the admin scope: the
    narrowing below is for the Teacher department only, so a principal logged in
    as admin is not accidentally restricted to one classroom.
    """
    if user is None or getattr(user, 'is_superuser', False) or getattr(user, 'is_staff', False):
        return False
    employee = teacher_employee(user)
    return employee is not None and employee.is_teacher


def teacher_assignments(employee, session=None):
    """The teacher's assignments for ``session`` (the running one by default)."""
    if employee is None:
        return TeacherAssignment.objects.none()
    assignments = TeacherAssignment.objects.filter(
        employee=employee, is_active=True,
    ).select_related('subject', 'institution')
    session = session or current_teaching_session(employee)
    if session:
        assignments = assignments.filter(session__iexact=session)
    return assignments


def current_teaching_session(employee):
    """The session the teacher is currently working in.

    The running academic session when the teacher has assignments there,
    otherwise the newest session they *do* have — so a teacher whose assignments
    were entered as '2025-2026' is not locked out on the first day of the new
    session.
    """
    this_year = current_academic_session()
    if employee is None:
        return this_year
    sessions = list(
        TeacherAssignment.objects.filter(employee=employee, is_active=True)
        .values_list('session', flat=True).distinct()
    )
    for value in sessions:
        if value and value.lower() == this_year.lower():
            return this_year
    if sessions:
        return sorted((value for value in sessions if value), reverse=True)[0]
    return this_year


def _scope_filter(assignments):
    """``Q`` covering every class/section pair of these assignments."""
    from django.db.models import Q

    query = Q(pk__in=[])
    for assignment in assignments:
        variants = class_filter_variants(assignment.admission_class)
        section = (assignment.section or '').strip()
        if section:
            query |= Q(admission_class__in=variants, section__iexact=section)
        else:
            query |= Q(admission_class__in=variants)
    return query


def teacher_students(employee, assignments=None):
    """The students in this teacher's assigned classes/sections."""
    if teacher_employee(getattr(employee, 'user', None)) is None and employee is not None:
        # A resigned/OSD employee keeps the row but loses the class list, so a
        # caller that passes the Employee directly cannot bypass the check.
        if employee.status != 'ACTIVE':
            return Student.objects.none()
    if employee is None:
        return Student.objects.none()
    assignments = list(assignments if assignments is not None else teacher_assignments(employee))
    if not assignments:
        return Student.objects.none()
    students = Student.objects.filter(
        is_archived=False, status='ACTIVE', institution=employee.institution_id,
    )
    return students.filter(_scope_filter(assignments)).distinct()


def teacher_subjects(employee, assignments=None):
    """The subjects this teacher is assigned to teach."""
    assignments = list(assignments if assignments is not None else teacher_assignments(employee))
    subject_ids = {assignment.subject_id for assignment in assignments}
    if not subject_ids:
        return Subject.objects.none()
    return Subject.objects.filter(pk__in=subject_ids).order_by('name')


def teacher_exams(employee, assignments=None):
    """Exams a teacher may open marks for: same institution, their classes.

    Section is deliberately ignored here — an exam is created per class (often
    for the whole class), and marks entry narrows by subject anyway. Narrowing
    by section as well would hide a class-wide exam from the section's teacher.
    """
    assignments = list(assignments if assignments is not None else teacher_assignments(employee))
    if not assignments:
        return Exam.objects.none()
    from django.db.models import Q

    query = Q(pk__in=[])
    for assignment in assignments:
        query |= Q(admission_class__in=class_filter_variants(assignment.admission_class))
    exams = Exam.objects.filter(institution=employee.institution_id).filter(query)
    sessions = {assignment.session for assignment in assignments if assignment.session}
    if sessions:
        exams = exams.filter(session__in=sessions)
    return exams.distinct().order_by('-session', '-exam_date', 'name')


def may_touch_student(employee, student):
    """True when ``student`` sits in one of this teacher's classes/sections."""
    if employee is None or student is None:
        return False
    if student.institution_id != employee.institution_id:
        return False
    return teacher_students(employee).filter(pk=student.pk).exists()


def may_touch_exam(employee, exam):
    """True when this exam is for one of the teacher's classes."""
    if employee is None or exam is None:
        return False
    return teacher_exams(employee).filter(pk=exam.pk).exists()


def may_touch_subject(employee, subject, assignments=None):
    if employee is None or subject is None:
        return False
    return teacher_subjects(employee, assignments).filter(pk=subject.pk).exists()


def teacher_correction_requests(employee, assignments=None):
    """Correction requests a teacher may read: their own classes' students.

    Scoped by student (not by who filed it) on purpose: the subject teacher has
    to see the application the office filed about *their* paper, otherwise
    nothing could ever be checked and submitted.
    """
    if employee is None:
        return MarkCorrectionRequest.objects.none()
    students = teacher_students(employee, assignments)
    return MarkCorrectionRequest.objects.filter(
        institution_id=employee.institution_id, student__in=students,
    )
