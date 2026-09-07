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

    The class filter is zero-padding tolerant ('9' matches '09') for the same
    reason as :func:`get_exam_students` — requirements and exams were written
    by different screens over the years.

    Returns (subjects_queryset, is_filtered).
    """
    from .models import Subject, SubjectRequirement

    effective_group = (group if group is not None else exam.group) or ''

    if exam.institution_id:
        requirements = SubjectRequirement.objects.filter(
            institution_id=exam.institution_id,
            admission_class__in=class_filter_variants(exam.admission_class),
        )
        if effective_group:
            # Group-neutral subjects (Bangla, English...) apply to every group.
            requirements = requirements.filter(Q(group='') | Q(group=effective_group))
        subject_ids = list(requirements.values_list('subject_id', flat=True).distinct())
        if subject_ids:
            return Subject.objects.filter(pk__in=subject_ids).order_by('name'), True

    return Subject.objects.all().order_by('name'), False


def religion_subject_map(exam, subjects):
    """{subject_pk: religion} for the religion papers among ``subjects``.

    A religion paper is a CONDITIONAL SubjectRequirement whose
    condition_religion is set (that is how Auto-populate creates Islam /
    Hindu), or — as a fallback — a subject in the RELIGION category whose name
    says which religion it is. Non-religion subjects are simply not in the map.
    """
    from .models import SubjectRequirement, parse_religion_label

    subjects = [subject for subject in subjects if subject is not None]
    if not subjects:
        return {}

    religion_by_pk = {}
    requirements = SubjectRequirement.objects.filter(
        institution_id=exam.institution_id,
        admission_class__in=class_filter_variants(exam.admission_class),
        requirement_type='CONDITIONAL',
        subject_id__in=[subject.pk for subject in subjects],
    ).exclude(condition_religion='')
    for requirement in requirements:
        label = parse_religion_label(requirement.condition_religion)
        if label:
            religion_by_pk[requirement.subject_id] = label

    for subject in subjects:
        if subject.pk not in religion_by_pk and subject.category == 'RELIGION':
            label = parse_religion_label(subject.name)
            if label:
                religion_by_pk[subject.pk] = label
    return religion_by_pk


def religion_paper_for(student, religion_by_pk):
    """The one religion paper this student sits, or ``None`` when the class has
    no religion paper assigned at all.

    Hindu students sit Hindu Religion & Moral Education; every other student
    (Islam, blank or any legacy value) sits Islam & Moral Education — and when
    the class does not have the student's own paper assigned, Islam is the
    default paper. A paper is never forced on a student of another religion.
    """
    from .models import student_religion

    if not religion_by_pk:
        return None
    wanted = student_religion(student.religion)
    for pk, label in religion_by_pk.items():
        if label == wanted:
            return pk
    return next((pk for pk, label in religion_by_pk.items() if label == 'Islam'), None)


def applicable_religion_papers(exam, subjects, students):
    """Split religion papers per student.

    Returns (kept_subjects, paper_by_student_pk, religion_by_pk):

    * ``kept_subjects`` — ``subjects`` minus religion papers that none of these
      students sit (e.g. Christian / Buddhist papers in a school that has no
      such students, or Hindu when the class has no Hindu student);
    * ``paper_by_student_pk`` — the religion paper each student actually sits;
    * ``religion_by_pk`` — every religion paper that was in ``subjects``.
    """
    religion_by_pk = religion_subject_map(exam, subjects)
    if not religion_by_pk:
        return list(subjects), {}, {}

    paper_by_student = {}
    used = set()
    for student in students:
        pk = religion_paper_for(student, religion_by_pk)
        paper_by_student[student.pk] = pk
        if pk is not None:
            used.add(pk)
    kept = [
        subject for subject in subjects
        if subject.pk not in religion_by_pk or subject.pk in used
    ]
    return kept, paper_by_student, religion_by_pk


def get_exam_subjects_for_students(exam, students, group=None):
    """``get_exam_subjects`` narrowed to the papers these students sit.

    Marks entry, Excel import and their templates must not offer religion
    papers no student in the exam sits (Christian / Buddhist papers in a school
    that has none), so a teacher never sees a subject they cannot use. Returns
    (subjects_list, is_filtered) like :func:`get_exam_subjects`.
    """
    subjects, is_filtered = get_exam_subjects(exam, group=group)
    subjects = list(subjects)
    kept, _paper_by_student, _religion_by_pk = applicable_religion_papers(exam, subjects, students)
    return kept, is_filtered


def get_exam_group_choices(exam):
    """Groups configured for this exam's institution + class, for the picker."""
    from .models import Student, SubjectRequirement

    if not exam.institution_id:
        return []
    codes = set(
        SubjectRequirement.objects.filter(
            institution_id=exam.institution_id,
            admission_class__in=class_filter_variants(exam.admission_class),
        ).exclude(group='').values_list('group', flat=True).distinct()
    )
    return [(code, label) for code, label in Student.GROUP_CHOICES if code in codes]


def get_subject_marks(exam, subject):
    """
    Returns the marks configuration for this exam+subject combination — the
    specific SubjectMarkSetting if one exists, otherwise the subject's own
    global defaults. Both expose the same interface (see ``MarksConfigMixin``):
    full_marks, the part columns, pass_marks, parts.

    The setting's class is matched zero-padding tolerant ('9' = '09'), with the
    exam's own spelling preferred, so a setting saved under either form is
    found and the same one wins every time.
    """
    from .models import SubjectMarkSetting

    exam_class = str(exam.admission_class)
    for cls in [exam_class] + [v for v in class_filter_variants(exam_class) if v != exam_class]:
        setting = SubjectMarkSetting.objects.filter(
            institution=exam.institution,
            admission_class=cls,
            subject=subject,
            exam_type=exam.exam_type,
        ).first()
        if setting:
            return setting

    return subject


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

    A result is only a Pass when the student passes every subject they sat
    individually; failing (or not sitting) one subject makes the whole result
    Fail with GPA 0.00, and the total-mark percentage and the class position
    are not counted for a failed result.

    Religion papers are per student: a Hindu student sits Hindu Religion &
    Moral Education while every other student sits Islam & Moral Education.
    Each student is graded on their own paper; the other religion column shows
    a dash and is never counted. Papers that nobody in the class sits are not
    printed at all.
    """
    from .models import ExamMark

    students = get_exam_students(exam)
    subjects, is_filtered = get_exam_subjects(exam)
    subjects = list(subjects) if is_filtered else _subjects_with_marks(exam)
    subjects, religion_paper, religion_by_pk = applicable_religion_papers(exam, subjects, students)

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
        my_paper = religion_paper.get(student.pk)

        for subject in subjects:
            if subject.pk in religion_by_pk and subject.pk != my_paper:
                # Another student's religion paper: printed as a plain dash,
                # never counted and never a fail for this student.
                subject_results.append({
                    'subject': subject, 'not_applicable': True, 'absent': True,
                    'obtained': None, 'full': None, 'percentage': None,
                    'grade': ABSENT, 'point': None, 'passed': False,
                    'failed_parts': [], 'parts': [], 'pass_marks': None,
                })
                continue

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
            overall_percentage = None
        elif has_fail:
            # One failed subject means the whole result is Fail: the total
            # percentage is not counted and no position is awarded.
            overall_gpa, overall_grade, status = Decimal('0.00'), 'F', 'Fail'
            overall_percentage = None
        else:
            overall_gpa = round(sum(gpa_points) / len(gpa_points), 2) if gpa_points else Decimal('0.00')
            overall_grade, _ = get_grade(float(overall_percentage))
            status = 'Pass'

        results.append({
            'student': student, 'subject_results': subject_results,
            'total_obtained': total_obtained, 'total_full': total_full,
            'percentage': round(float(overall_percentage), 2) if overall_percentage is not None else None,
            'gpa': overall_gpa,
            'grade': overall_grade, 'status': status,
            # "has marks" means there is something to print: a student whose only
            # rows sit in subjects outside this exam still counts as No Marks.
            'has_marks': bool(attempted),
            'absent_subject_count': sum(
                1 for r in subject_results if r['absent'] and not r.get('not_applicable')
            ),
            'position': None,
        })

    # Only a student who passed every subject individually is placed — the
    # position is part of the result, so a failed result is not counted here
    # any more than the percentage is. 'No Marks' students stay unranked too.
    ranked = sorted(
        (result for result in results if result['status'] == 'Pass'),
        key=lambda result: (-result['gpa'], -result['total_obtained'])
    )
    previous_key = None
    for index, result in enumerate(ranked):
        key = (result['gpa'], result['total_obtained'])
        result['position'] = ranked[index - 1]['position'] if index and key == previous_key else index + 1
        previous_key = key
    return subjects, ranked + [result for result in results if result['position'] is None]


def _subjects_with_marks(exam):
    """Fallback column list when no subject assignments are configured."""
    from .models import ExamMark, Subject

    return list(Subject.objects.filter(
        id__in=ExamMark.objects.filter(exam=exam).values_list('subject_id', flat=True).distinct()
    ).order_by('name'))
