"""Marking rules shared by every exam route.

Marks entry, Excel import, seat planning and the result pages must agree on two
things or the school ends up with a different set of students/subjects per
screen: who belongs to an exam, and how a mark turns into a grade. Both live
here so there is exactly one implementation of each.
"""
from decimal import Decimal

from django.db.models import Q


def class_filter_variants(value):
    """Every string form of a class number that means the same class.

    ``admission_class`` is a CharField written by several screens over the
    years, so '9' and '09' both exist in the database. Filtering on one of
    them silently drops students.
    """
    value = str(value).strip()
    variants = {value}
    if value.isdigit():
        variants.add(value.zfill(2))
        variants.add(str(int(value)))
    return list(variants)


def get_exam_students(exam, group=None):
    """The one and only student list an exam works on.

    Scoped to the exam's institution, class (zero-padding tolerant), section
    and group. ``group`` overrides the exam's own group for exams created
    without one, so the group picker on the marks pages drives the same filter
    as the subject list.
    """
    from .models import Student

    students = Student.objects.filter(is_archived=False)
    if exam.institution_id:
        students = students.filter(institution_id=exam.institution_id)
    students = students.filter(
        admission_class__in=class_filter_variants(exam.admission_class)
    )
    if exam.section:
        students = students.filter(section__iexact=exam.section.strip())
    effective_group = (group if group is not None else exam.group) or ''
    if effective_group:
        students = students.filter(group=effective_group)
    return students.order_by('roll_no', 'name')


def get_exam_subjects(exam, group=None):
    """Subjects that actually apply to this exam's institution + class + group.

    Marks entry must be group-aware: a Science exam should not offer Business
    Studies. Falls back to every subject when no SubjectRequirement rows are
    configured yet, so marks entry never gets blocked on an unconfigured class.

    ``group`` overrides the exam's own group, for exams that were created
    without one (the marks pages then let the user pick a group). When neither
    the exam nor the caller specifies a group, every group's subjects for that
    class are returned.

    Returns (subjects_queryset, is_filtered).
    """
    from .models import Subject, SubjectRequirement

    effective_group = (group if group is not None else exam.group) or ''

    if exam.institution_id:
        requirements = SubjectRequirement.objects.filter(
            institution_id=exam.institution_id,
            admission_class=str(exam.admission_class),
        )
        if effective_group:
            # Group-neutral subjects (Bangla, English...) apply to every group.
            requirements = requirements.filter(Q(group='') | Q(group=effective_group))
        subject_ids = list(requirements.values_list('subject_id', flat=True).distinct())
        if subject_ids:
            return Subject.objects.filter(pk__in=subject_ids).order_by('name'), True

    return Subject.objects.all().order_by('name'), False


def get_exam_group_choices(exam):
    """Groups configured for this exam's institution + class, for the picker."""
    from .models import Student, SubjectRequirement

    if not exam.institution_id:
        return []
    codes = set(
        SubjectRequirement.objects.filter(
            institution_id=exam.institution_id,
            admission_class=str(exam.admission_class),
        ).exclude(group='').values_list('group', flat=True).distinct()
    )
    return [(code, label) for code, label in Student.GROUP_CHOICES if code in codes]


def get_subject_marks(exam, subject):
    """
    Returns the marks configuration for this exam+subject combination — the
    specific SubjectMarkSetting if one exists, otherwise the subject's own
    global defaults. Both expose the same interface (see ``MarksConfigMixin``):
    full_marks, the part columns, pass_marks, parts.
    """
    from .models import SubjectMarkSetting

    setting = SubjectMarkSetting.objects.filter(
        institution=exam.institution,
        admission_class=exam.admission_class,
        subject=subject,
        exam_type=exam.exam_type,
    ).first()

    return setting if setting else subject


def get_grade(percentage):
    """Return the letter grade and GPA point for a percentage."""
    if percentage >= 80:
        return 'A+', Decimal('5.00')
    if percentage >= 70:
        return 'A', Decimal('4.00')
    if percentage >= 60:
        return 'A-', Decimal('3.50')
    if percentage >= 50:
        return 'B', Decimal('3.00')
    if percentage >= 40:
        return 'C', Decimal('2.00')
    if percentage >= 33:
        return 'D', Decimal('1.00')
    return 'F', Decimal('0.00')


ABSENT = '-'


def absent_subject_fails_result():
    """Should a subject with no mark at all fail the student?

    This is the NCTB/SSC reading: a candidate who does not sit an assigned
    subject has not passed it, so the subject is graded F and the result is
    Fail — a blank box is not a free exemption. Set
    ``EXAM_ABSENT_SUBJECT_FAILS=False`` (environment variable, see
    ``.env.example``) to go back to ignoring un-entered subjects entirely:
    then the dash stays a dash, the subject is left out of the total and the
    student can still pass on the papers they sat.
    """
    from django.conf import settings

    return getattr(settings, 'EXAM_ABSENT_SUBJECT_FAILS', True)


def _part_breakdown(mark, marks_config):
    """Per-part detail for one student's mark.

    A part that is configured but was never entered counts as a failure: the
    school asked for a practical paper and there is no practical mark, so the
    subject cannot be declared passed on the strength of the theory alone.
    """
    from .models import ExamMark

    parts = []
    for part in marks_config.parts:
        obtained = getattr(mark, ExamMark.obtained_field(part['key'])) if mark else None
        pass_marks = marks_config.part_pass_marks(part['max_marks'])
        missing = obtained is None
        parts.append({
            'key': part['key'],
            'label': part['label'],
            'max_marks': part['max_marks'],
            'obtained': obtained,
            'pass_marks': pass_marks,
            'missing': missing,
            'passed': (not missing) and obtained >= pass_marks,
        })
    return parts


def compute_subject_result(mark, marks_config):
    """Grade for a single (student, subject) pair.

    ``mark`` is None when nothing at all was entered for the subject, which
    means the student did not sit it. That is *not* the same as a 0 — a blank
    row shows as a dash and is left out of the total and the GPA, while a real
    0 is counted and fails the subject.
    """
    if mark is None:
        if absent_subject_fails_result():
            # Not entered = the paper was not passed: graded F and counted as
            # 0 out of Full Marks, so the total and the percentage tell the
            # whole story. The cell still shows a dash, never a 0.
            return {
                'obtained': Decimal('0'), 'full': marks_config.full_marks,
                'percentage': 0.0, 'grade': 'F', 'point': Decimal('0.00'),
                'passed': False, 'absent': True, 'failed_parts': [],
                'parts': [], 'pass_marks': marks_config.pass_marks,
            }
        return {
            'obtained': None, 'full': marks_config.full_marks,
            'percentage': None, 'grade': ABSENT, 'point': None,
            'passed': False, 'absent': True, 'failed_parts': [],
            'parts': [], 'pass_marks': marks_config.pass_marks,
        }

    obtained = Decimal(str(mark.marks_obtained or 0))
    full = Decimal(str(marks_config.full_marks or 0))
    percentage = (obtained / full * 100) if full else Decimal('0')
    grade, point = get_grade(float(percentage))

    parts = _part_breakdown(mark, marks_config)
    failed_parts = [part for part in parts if not part['passed']]
    total_passed = obtained >= Decimal(str(marks_config.pass_marks))
    # The part rule is opt-in per subject/exam type; the overall pass mark
    # always applies.
    passed = total_passed and (not failed_parts if marks_config.require_all_parts_pass else True)
    if not passed:
        grade, point = 'F', Decimal('0.00')

    return {
        'obtained': obtained, 'full': marks_config.full_marks,
        'percentage': round(float(percentage), 2), 'grade': grade, 'point': point,
        'passed': passed, 'absent': False,
        'failed_parts': [part['label'] for part in failed_parts],
        'parts': parts, 'pass_marks': marks_config.pass_marks,
        'total_passed': total_passed,
    }


def unassigned_mark_subjects(exam, subjects):
    """Subjects that hold marks for this exam but are not assigned to it.

    The result sheet only prints the exam's own subjects, so without this the
    stray marks would simply vanish. The page shows them as a notice instead.
    """
    from .models import ExamMark, Subject

    marks = ExamMark.objects.filter(exam=exam)
    if marks.exists():
        return Subject.objects.filter(
            id__in=marks.values_list('subject_id', flat=True).distinct(),
        ).exclude(id__in=[subject.pk for subject in subjects]).order_by('name')
    return Subject.objects.none()


def build_exam_results(exam):
    """Compute every student's result for one exam.

    Returns (subjects, results). Only the subjects assigned to the exam's class
    and group are printed, and only the subjects a student actually sat count
    towards their total and GPA.
    """
    from .models import ExamMark

    students = get_exam_students(exam)
    subjects, is_filtered = get_exam_subjects(exam)
    subjects = list(subjects) if is_filtered else _subjects_with_marks(exam)

    marks = {}
    for mark in ExamMark.objects.filter(exam=exam).select_related('student', 'subject'):
        marks.setdefault(mark.student_id, {})[mark.subject_id] = mark

    results = []
    for student in students:
        student_marks = marks.get(student.pk, {})
        subject_results = []
        total_obtained = Decimal('0')
        total_full = Decimal('0')
        gpa_points = []
        has_fail = False

        for subject in subjects:
            marks_config = get_subject_marks(exam, subject)
            result = compute_subject_result(student_marks.get(subject.pk), marks_config)
            result['subject'] = subject
            counted = not result['absent'] or result['obtained'] is not None
            if counted:
                # An absent subject arrives here as 0 / Full Marks and fails,
                # which is what drags the result down to F + GPA 0.00.
                total_obtained += result['obtained']
                total_full += Decimal(str(result['full']))
                has_fail = has_fail or not result['passed']
                gpa_points.append(result['point'])
            subject_results.append(result)

        attempted = [row for row in subject_results if not row['absent']]
        overall_percentage = (total_obtained / total_full * 100) if total_full else Decimal('0')
        if not attempted:
            # No mark entered anywhere: the student did not sit this exam at
            # all. That stays 'No Marks' rather than 'Fail' — a completely
            # absent candidate is an attendance problem, not a graded result,
            # and must not appear in the ranking with a fabricated 0.00 GPA.
            overall_gpa, overall_grade, status = None, ABSENT, 'No Marks'
        elif has_fail:
            overall_gpa, overall_grade, status = Decimal('0.00'), 'F', 'Fail'
        else:
            overall_gpa = round(sum(gpa_points) / len(gpa_points), 2) if gpa_points else Decimal('0.00')
            overall_grade, _ = get_grade(float(overall_percentage))
            status = 'Pass'

        results.append({
            'student': student, 'subject_results': subject_results,
            'total_obtained': total_obtained, 'total_full': total_full,
            'percentage': round(float(overall_percentage), 2), 'gpa': overall_gpa,
            'grade': overall_grade, 'status': status,
            # "has marks" means there is something to print: a student whose only
            # rows sit in subjects outside this exam still counts as No Marks.
            'has_marks': bool(attempted),
            'absent_subject_count': sum(1 for r in subject_results if r['absent']),
            'position': None,
        })

    # Only students with a real GPA are placed: a No Marks/Absent student has
    # gpa None and would blow up the sort.
    ranked = sorted(
        (result for result in results if result['gpa'] is not None),
        key=lambda result: (-result['gpa'], -result['total_obtained'])
    )
    previous_key = None
    for index, result in enumerate(ranked):
        key = (result['gpa'], result['total_obtained'])
        result['position'] = ranked[index - 1]['position'] if index and key == previous_key else index + 1
        previous_key = key
    return subjects, ranked + [result for result in results if result['gpa'] is None]


def _subjects_with_marks(exam):
    """Fallback column list when no subject assignments are configured."""
    from .models import ExamMark, Subject

    return list(Subject.objects.filter(
        id__in=ExamMark.objects.filter(exam=exam).values_list('subject_id', flat=True).distinct()
    ).order_by('name'))
