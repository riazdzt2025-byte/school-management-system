"""Marking rules shared by every exam route.

Marks entry, Excel import, seat planning and the result pages must agree on two
things or the school ends up with a different set of students/subjects per
screen: who belongs to an exam, and how a mark turns into a grade. Both live
here so there is exactly one implementation of each.
"""
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Q, F


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

    # D-MIS (2026-09-17): TC / Discontinued / inactive students are not part
    #    # of the published register — they would otherwise show AB/F for every subject.
    students = Student.objects.filter(is_archived=False, status='ACTIVE')
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
    # Register order (EX-02 rule): numeric roll — ``roll_no`` is an
    # IntegerField, so SQL sorts it numerically — with name and pk as stable
    # tie-breaks, and students *without* a roll always last (``nulls_last``;
    # a plain ``order_by('roll_no')`` would put NULLs first). Seat plans,
    # signature sheets and the marks-entry list all follow this order.
    return students.order_by(F('roll_no').asc(nulls_last=True), 'name', 'pk')


def get_exam_subjects(exam, group=None):
    """Subjects that actually apply to this exam's institution + class + group.

    Marks entry must be group-aware: a Science exam should not offer Business
    Studies. Only the subjects assigned through Subject Assignment rows
    (SubjectRequirement) are ever returned — there is deliberately **no**
    fallback to the whole Subject master list. A class with no subjects
    assigned gets an empty list, and the marks/result pages tell the user to
    assign subjects first instead of silently offering every subject in the
    system.

    ``group`` overrides the exam's own group, for exams that were created
    without one (the marks pages then let the user pick a group). When neither
    the exam nor the caller specifies a group, every group's subjects for that
    class are returned.

    The class filter is zero-padding tolerant ('9' matches '09') for the same
    reason as :func:`get_exam_students` — requirements and exams were written
    by different screens over the years.

    Returns (subjects_list, is_filtered): ``is_filtered`` is True whenever the
    class has at least one SubjectRequirement row (so the list is the assigned
    one, even if group narrowing leaves it empty) and False when nothing at
    all is assigned.
    """
    from .models import Subject, SubjectRequirement

    effective_group = (group if group is not None else exam.group) or ''

    if not exam.institution_id:
        return [], False

    requirements = SubjectRequirement.objects.filter(
        institution_id=exam.institution_id,
        admission_class__in=class_filter_variants(exam.admission_class),
    )
    if effective_group:
        # Group-neutral subjects (Bangla, English...) apply to every group.
        requirements = requirements.filter(Q(group='') | Q(group=effective_group))
    subject_ids = list(requirements.values_list('subject_id', flat=True).distinct())
    if not subject_ids:
        return [], False
    subject_ids = list(active_exam_subject_ids(exam, subject_ids, group=effective_group))
    if not subject_ids:
        return [], True
    # The printed register follows the examination subject serial/code
    # (101, 102, 107, 108, 136, 150 in the school's result format), not
    # alphabetical subject names. This keeps marks entry, imports and the
    # result sheet in the same predictable order.
    return list(Subject.objects.filter(pk__in=subject_ids).order_by('code', 'name')), True


def active_exam_subject_ids(exam, subject_ids, group=None):
    """Subject ids still enabled in Mark Evaluation for this exam type.

    Mark Evaluation has an Active/Count checkbox per Institution + Class +
    Subject + Exam Type + Group. A missing row means the subject remains active so old
    data behaves exactly as before; only an explicit unchecked setting disables
    a subject for marks entry/import/result calculation.

    Group-aware (EX-03): the resolution is group-specific -> blank-group
    default. For an exam in group SCI, the SCI row decides; otherwise the
    blank-group row; otherwise active.
    """
    from .models import SubjectMarkSetting

    subject_ids = list(subject_ids)
    if not subject_ids:
        return set()
    exam_type = getattr(exam, 'exam_type', '') or ''
    institution_id = getattr(exam, 'institution_id', None)
    admission_class = getattr(exam, 'admission_class', '')
    if not exam_type or not institution_id or not admission_class:
        return set(subject_ids)

    effective_group = (group if group is not None else getattr(exam, 'group', '')) or ''
    preferred_class = str(admission_class).strip()
    class_variants = class_filter_variants(preferred_class)
    # Build rank for class and group priority
    class_rank = {preferred_class: 0}
    for value in class_variants:
        class_rank.setdefault(value, len(class_rank))
    # Group priority: exact group (0) then blank (1)
    def group_rank(g):
        if effective_group and g == effective_group:
            return 0
        if g == '':
            return 1
        return 2

    # Fetch all candidate rows (exact group + blank fallback)
    group_filter = [effective_group, ''] if effective_group else ['']
    settings = SubjectMarkSetting.objects.filter(
        institution_id=institution_id,
        admission_class__in=class_variants,
        subject_id__in=subject_ids,
        exam_type=exam_type,
        group__in=group_filter,
    ).values('subject_id', 'admission_class', 'group', 'is_active')

    # Sort by group priority then class rank, so the prevailing row is first.
    active_by_subject = {}
    for row in sorted(settings, key=lambda item: (group_rank(item['group']), class_rank.get(item['admission_class'], 99))):
        active_by_subject.setdefault(row['subject_id'], row['is_active'])

    return {subject_id for subject_id in subject_ids if active_by_subject.get(subject_id, True)}


def no_subjects_assigned_message(exam):
    """The message every marks/result page shows when a class has no subjects
    assigned yet. The pages link to the Subject Assignments page filtered to
    the exam's own institution + class.
    """
    return (
        f"No subjects are assigned to Class {exam.admission_class} yet"
        " — assign them from the Subject Assignments page first."
    )


# ---- Why a marks/result page has no subject to offer ----------------------
# An empty subject list has three different causes and three different fixes.
# Showing "assign subjects" for all three sends the user to the wrong page:
# the subjects may already be assigned and simply switched off in Mark
# Evaluation, or assigned and active but not selected by any student.
SUBJECTS_NOT_ASSIGNED = 'not_assigned'
SUBJECTS_ALL_DISABLED = 'all_disabled'
SUBJECTS_NO_STUDENT = 'no_student'


def exam_type_label(exam):
    """Human name of the exam type, tolerating the ``SimpleNamespace`` exam
    look-alikes the marks/evaluation screens build (they carry ``exam_type``
    but not Django's ``get_FOO_display`` helper)."""
    display = getattr(exam, 'get_exam_type_display', None)
    if callable(display):
        try:
            return display()
        except Exception:
            pass
    from .models import Exam

    raw = getattr(exam, 'exam_type', '') or ''
    return dict(Exam.EXAM_TYPE_CHOICES).get(raw, raw or 'this exam type')


def subject_availability_diagnosis(exam, students=None, group=None):
    """Explain *why* this exam has no subject to enter marks for.

    Returns ``(reason, message)`` where ``reason`` is one of
    :data:`SUBJECTS_NOT_ASSIGNED` / :data:`SUBJECTS_ALL_DISABLED` /
    :data:`SUBJECTS_NO_STUDENT`, and ``message`` is a sentence that names the
    cause and the screen that fixes it. Views turn ``reason`` into the right
    link (or, when the user has no permission for it, into the name of the
    department that does).

    ``students`` may be passed in to reuse a list the view already loaded.
    The function never raises for a partial exam object — a missing
    institution is reported as "nothing assigned", matching
    :func:`get_exam_subjects`.
    """
    from .models import SubjectRequirement

    if not getattr(exam, 'institution_id', None):
        return SUBJECTS_NOT_ASSIGNED, no_subjects_assigned_message(exam)

    class_variants = class_filter_variants(exam.admission_class)
    effective_group = (group if group is not None else getattr(exam, 'group', '')) or ''
    requirements = SubjectRequirement.objects.filter(
        institution_id=exam.institution_id,
        admission_class__in=class_variants,
    )
    if effective_group:
        requirements = requirements.filter(Q(group='') | Q(group=effective_group))
    requirement_rows = list(requirements.values('subject_id', 'requirement_type'))
    if not requirement_rows:
        return SUBJECTS_NOT_ASSIGNED, no_subjects_assigned_message(exam)

    assigned_ids = list({row['subject_id'] for row in requirement_rows})
    active_ids = set(active_exam_subject_ids(exam, assigned_ids, group=effective_group))
    if not active_ids:
        return SUBJECTS_ALL_DISABLED, (
            f"All {len(assigned_ids)} subject(s) assigned to Class {exam.admission_class}"
            f" are switched off in Mark Evaluation for {exam_type_label(exam)}"
            " — tick \"Count\" beside the subjects that should carry marks, then come back."
        )

    if students is None:
        students = list(get_exam_students(exam, group=group))
    if not students:
        scope = f" Class {exam.admission_class}"
        if effective_group:
            scope += f" ({effective_group} group)"
        return SUBJECTS_NO_STUDENT, (
            f"No admitted student matches{scope}, so there is nobody to enter"
            " marks for — admit the students first."
        )

    subjects, _is_filtered = get_exam_subjects(exam, group=group)
    subjects = [subject for subject in subjects if subject.pk in active_ids]
    student_subject_ids = get_student_subject_ids(
        exam, students, subjects=subjects, group=group,
    )
    used_ids = set().union(*(ids for ids in student_subject_ids.values())) if students else set()
    if used_ids:
        # Subjects are available — the caller should not be showing an empty
        # state at all.
        return '', ''

    # Assigned and active, but no student in this class/group takes any of
    # them. With optional-only rows that means the office has not recorded a
    # subject choice for these students yet; otherwise the group simply does
    # not match.
    optional_only = all(
        row['requirement_type'] == 'OPTIONAL'
        for row in requirement_rows if row['subject_id'] in active_ids
    )
    if optional_only:
        return SUBJECTS_NO_STUDENT, (
            f"Class {exam.admission_class} only has optional subjects assigned and no"
            " student has picked one yet — record each student's subject choice"
            " (Office → Students → Edit student) before entering marks."
        )
    return SUBJECTS_NO_STUDENT, (
        f"The subjects assigned to Class {exam.admission_class} do not apply to any"
        " student in this class/group — check the group on the assignment rows and"
        " the students' own group."
    )


def published_exams_affected_by_assignment(institution_id, admission_class, group=''):
    """Published exams for this institution + class (+ group) that already hold
    marks.

    Adding a subject to a class is read at result time, not written into the
    exams, so a new row reaches results that were published earlier too. The
    Subject Assignments page uses this to warn the office *before* the change
    is saved, instead of letting a published Pass quietly turn into a Fail.
    """
    from .models import Exam, ExamMark

    if not institution_id:
        return []
    exams = Exam.objects.filter(
        institution_id=institution_id,
        admission_class__in=class_filter_variants(admission_class),
        is_published=True,
    )
    if group:
        exams = exams.filter(Q(group=group) | Q(group=''))
    marked_exam_ids = set(
        ExamMark.objects.filter(exam__in=exams).values_list('exam_id', flat=True).distinct()
    )
    return [exam for exam in exams.order_by('-session', '-exam_date', '-id') if exam.pk in marked_exam_ids]


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
    """The one religion paper this student sits, or ``None`` when the class
    does not assign that student's own paper.

    Hindu students sit Hindu Religion & Moral Education; every other student
    (Islam, blank or any legacy value) sits Islam & Moral Education. When the
    class does not have the student's *own* paper assigned, the answer is
    ``None`` — no other religion's paper is ever substituted: the result sheet
    then prints a dash in the merged Religion column, and marks entry / Excel
    import have no paper to offer that student. A paper is never forced on a
    student of another religion.
    """
    from .models import student_religion

    if not religion_by_pk:
        return None
    wanted = student_religion(student.religion)
    return next(
        (pk for pk, label in religion_by_pk.items() if label == wanted),
        None,
    )


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


def get_student_subject_ids(exam, students, subjects=None, group=None):
    """Return the subjects that each student actually takes.

    SubjectRequirement rows describe the curriculum offered to a class. A
    student's admission choices add the selected optional subjects; mandatory
    and religion-conditioned rows are derived for the student's own group and
    religion. Older students with no choice rows fall back to all applicable
    class requirements so legacy data remains usable.
    """
    from .models import StudentSubjectChoice, SubjectRequirement, parse_religion_label, student_religion

    students = list(students)
    if subjects is None:
        subjects, _is_filtered = get_exam_subjects(exam, group=group)
    subjects = list(subjects)
    base_subject_ids = {subject.pk for subject in subjects if getattr(subject, 'pk', None)}
    if not students or not base_subject_ids:
        return {student.pk: set() for student in students}

    student_ids = [student.pk for student in students]
    effective_group = (group if group is not None else exam.group) or ''
    class_variants = class_filter_variants(exam.admission_class)

    requirement_rows = list(SubjectRequirement.objects.filter(
        institution_id=exam.institution_id,
        admission_class__in=class_variants,
        subject_id__in=base_subject_ids,
    ).values(
        'subject_id', 'group', 'requirement_type', 'condition_religion',
        'subject__category', 'subject__name',
    ))
    choice_subjects = defaultdict(set)
    choice_present = set()
    choice_rows = StudentSubjectChoice.objects.filter(
        student_id__in=student_ids,
        requirement__institution_id=exam.institution_id,
        requirement__admission_class__in=class_variants,
        requirement__subject_id__in=base_subject_ids,
    ).values(
        'student_id', 'requirement__subject_id', 'requirement__group',
    )
    student_by_id = {student.pk: student for student in students}
    for row in choice_rows:
        student = student_by_id.get(row['student_id'])
        if student is None:
            continue
        student_group = effective_group or (student.group or '')
        requirement_group = row['requirement__group'] or ''
        if requirement_group and requirement_group != student_group:
            continue
        choice_present.add(student.pk)
        choice_subjects[student.pk].add(row['requirement__subject_id'])

    assigned = {}
    for student in students:
        student_group = effective_group or (student.group or '')
        wanted_religion = student_religion(student.religion)
        auto_subjects = set()

        for row in requirement_rows:
            requirement_group = row['group'] or ''
            if requirement_group and requirement_group != student_group:
                continue
            label = ''
            if row['condition_religion'] and row['requirement_type'] == 'CONDITIONAL':
                label = parse_religion_label(row['condition_religion'])
            elif row['subject__category'] == 'RELIGION':
                label = parse_religion_label(row['subject__name'])

            if row['requirement_type'] == 'MANDATORY':
                if not label or label == wanted_religion:
                    auto_subjects.add(row['subject_id'])
            elif row['requirement_type'] == 'CONDITIONAL' and label == wanted_religion:
                auto_subjects.add(row['subject_id'])

        # Mandatory and the student's own religion paper come from the class
        # assignment table. Optional papers only count when the student (or
        # office edit) actually selected them at admission. Never fall back to
        # every optional on the class catalogue — that is why unused electives
        # and other-group papers used to appear on marks/result screens.
        assigned[student.pk] = set(auto_subjects)
        if student.pk in choice_present:
            assigned[student.pk] |= choice_subjects[student.pk]
    return assigned


def get_exam_subjects_for_students(exam, students, group=None):
    """``get_exam_subjects`` narrowed to subjects assigned to these students.

    Marks entry, Excel import and their templates must not offer optional
    subjects not selected during admission, or religion papers no student in
    the exam sits (Christian / Buddhist papers in a school that has none), so a
    teacher never sees a subject they cannot use. Returns (subjects_list,
    is_filtered) like :func:`get_exam_subjects`.
    """
    subjects, is_filtered = get_exam_subjects(exam, group=group)
    subjects = list(subjects)
    student_subject_ids = get_student_subject_ids(
        exam, students, subjects=subjects, group=group,
    )
    used_ids = set().union(*(ids for ids in student_subject_ids.values()))
    subjects = [subject for subject in subjects if subject.pk in used_ids]
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


def get_subject_marks(exam, subject, group=None):
    """
    Returns the marks configuration for this exam+subject combination — the
    specific SubjectMarkSetting if one exists, otherwise the subject's own
    global defaults. Both expose the same interface (see ``MarksConfigMixin``):
    full_marks, the part columns, pass_marks, parts.

    Resolution chain (group-aware, EX-03):
      1) group-specific row (institution+class+subject+exam_type+group)
      2) blank-group default (group='')
      3) Subject global defaults

    ``group`` overrides ``exam.group`` when the exam was created without a
    group (the marks pages let the user pick a group). The setting's class is
    matched zero-padding tolerant ('9' = '09'), with the exam's own spelling
    preferred, so a setting saved under either form is found and the same one
    wins every time.
    """
    from .models import SubjectMarkSetting

    effective_group = (group if group is not None else getattr(exam, 'group', '')) or ''
    exam_class = str(exam.admission_class)
    class_candidates = [exam_class] + [v for v in class_filter_variants(exam_class) if v != exam_class]
    # Group candidates in priority order: exact group first, then blank fallback.
    if effective_group:
        group_candidates = [effective_group, '']
    else:
        group_candidates = ['']
    for grp in group_candidates:
        for cls in class_candidates:
            setting = SubjectMarkSetting.objects.filter(
                institution=exam.institution,
                admission_class=cls,
                subject=subject,
                exam_type=exam.exam_type,
                group=grp,
            ).first()
            if setting:
                return setting
    return subject

def resolve_mark_setting(institution, admission_class, subject, exam_type, group=''):
    """Low-level helper for the resolution chain used by bulk queries.

    Returns the SubjectMarkSetting that applies for (institution, class,
    subject, exam_type, group) or None when only the Subject defaults apply.
    Mirrors :func:`get_subject_marks` without needing an Exam object.
    """
    from .models import SubjectMarkSetting

    group = (group or '').strip()
    admission_class = str(admission_class).strip()
    class_candidates = [admission_class] + [v for v in class_filter_variants(admission_class) if v != admission_class]
    group_candidates = [group, ''] if group else ['']
    for grp in group_candidates:
        for cls in class_candidates:
            setting = SubjectMarkSetting.objects.filter(
                institution=institution,
                admission_class=cls,
                subject=subject,
                exam_type=exam_type,
                group=grp,
            ).first()
            if setting:
                return setting
    return None


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


GPA_QUANTUM = Decimal('0.01')
GPA_MAXIMUM = Decimal('5.00')
FOURTH_SUBJECT_BONUS_FLOOR = Decimal('2.00')


def calculate_final_gpa(main_gpa_points, fourth_subject_point=None):
    """Return the capped, two-place GPA for the main + fourth-subject policy.

    A student is graded on their main subjects only.  One selected
    ``Subject.category == 'FOURTH'`` paper can add the part of its point above
    2.00 to the *main* point total before division by the number of main
    subjects.  A fourth-subject F has point 0.00, therefore earns no bonus but
    never fails the main result.  The published GPA is always capped at 5.00.

    Decimal ``ROUND_HALF_UP`` makes the two-place display deterministic.  This
    helper deliberately contains no 4.90-to-5.00 benefit: that former rule was
    replaced by the owner-confirmed fourth-subject policy on 2026-09-23.
    """
    main_gpa_points = [Decimal(str(point)) for point in main_gpa_points]
    if not main_gpa_points:
        return Decimal('0.00')
    fourth_point = Decimal(str(fourth_subject_point or 0))
    fourth_bonus = max(Decimal('0.00'), fourth_point - FOURTH_SUBJECT_BONUS_FLOOR)
    raw_gpa = (sum(main_gpa_points) + fourth_bonus) / len(main_gpa_points)
    return min(
        raw_gpa.quantize(GPA_QUANTUM, rounding=ROUND_HALF_UP),
        GPA_MAXIMUM,
    )


def fourth_subject_configuration_errors(exam, group=None):
    """Describe students who selected more than one fourth subject for an exam.

    There may be several FOURTH papers in a school's catalogue so pupils can
    choose between them, but the approved policy permits exactly one per
    student.  Publishing calls this helper and refuses a bad configuration
    before a result could be issued with an arbitrary double bonus.
    """
    students = list(get_exam_students(exam, group=group))
    subjects, _is_filtered = get_exam_subjects(exam, group=group)
    selected_ids = get_student_subject_ids(exam, students, subjects=subjects, group=group)
    fourth_names = {
        subject.pk: subject.name for subject in subjects
        if subject.category == 'FOURTH'
    }
    errors = []
    for student in students:
        selected_fourth = sorted(
            fourth_names[subject_id]
            for subject_id in selected_ids.get(student.pk, set())
            if subject_id in fourth_names
        )
        if len(selected_fourth) > 1:
            errors.append(f"{student.name} (roll {student.roll_no or '—'}): {', '.join(selected_fourth)}")
    return errors


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


RELIGION_COLUMN_CODE = 'REL'


class ReligionColumn:
    """The single 'Religion' (REL) result column.

    Islam and Hindu Religion & Moral Education are two assigned subjects, but
    the result sheet prints one Religion column: each student's cell shows the
    result of *their own* religion paper (Hindu students sit the Hindu paper,
    everyone else the Islam paper) — the two papers are never two columns.

    A student whose own paper is not assigned to the class (``paper_for``
    returns ``None``) gets a plain dash: never a fail, never counted towards
    the total or the GPA, and never an "absent subject".
    """

    code = RELIGION_COLUMN_CODE
    name = 'Religion & Moral Education'
    is_religion_column = True

    def __init__(self, papers_by_label, religion_by_pk):
        # label ('Islam' / 'Hindu' / ...) -> the Subject assigned for it.
        self.papers_by_label = dict(papers_by_label)
        self.religion_by_pk = dict(religion_by_pk)
        self.subjects = list(self.papers_by_label.values())
        self.paper_by_pk = {paper.pk: paper for paper in self.subjects}

    @property
    def pk(self):
        # The column has no row in the Subject table; use the REL code as a
        # stable, non-numeric identifier wherever a subject-like key is handy.
        return self.code

    def paper_for(self, student):
        """The Subject this student sits, or ``None`` when their own paper is
        not assigned for the class (that student gets a never-counted dash)."""
        pk = religion_paper_for(student, self.religion_by_pk)
        return self.paper_by_pk.get(pk) if pk else None

    def paper_for_label(self, label):
        return self.papers_by_label.get(label)

    def header_marks_config(self, exam, group=None):
        """Full Marks for the column header: prefer the Islam paper's exam
        setting, then any other assigned paper — the papers share the same
        marks structure in every real curriculum."""
        paper = (
            self.paper_for_label('Islam')
            or next(iter(self.papers_by_label.values()), None)
        )
        return get_subject_marks(exam, paper, group=group) if paper else None

    def __str__(self):
        return self.name


def unassigned_mark_subjects(exam, subjects, group=None):
    """Subjects that hold marks for this exam but are not assigned to any
    student in the exam's admission subject scope.

    The result sheet only prints the exam's own student-assigned subjects, so
    without this the stray marks would simply vanish. The page shows them as a
    notice instead.
    ``subjects`` may include a :class:`ReligionColumn`, whose merged papers
    count as assigned so marks in either religion paper never look stray.
    """
    from .models import ExamMark, Subject

    assigned_ids = set()
    for subject in subjects:
        if isinstance(subject, ReligionColumn):
            assigned_ids.update(paper.pk for paper in subject.subjects)
        elif subject is not None:
            assigned_ids.add(subject.pk)

    marks = ExamMark.objects.filter(exam=exam)
    effective_group = (group if group is not None else exam.group) or ''
    if effective_group:
        marks = marks.filter(student__group=effective_group)
    if marks.exists():
        return Subject.objects.filter(
            id__in=marks.values_list('subject_id', flat=True).distinct(),
        ).exclude(id__in=assigned_ids).order_by('name')
    return Subject.objects.none()


def marked_subject_ids_for_exam(exam, students=None, group=None):
    """Subject ids that hold at least one mark for a student of this exam.

    A subject is part of an exam's result only once something has actually been
    entered for it. Subject assignments are keyed to the class, not to the
    exam, and are read at result time — so without this a subject assigned to
    the class *after* an exam was published would arrive as a brand-new column
    holding nothing, and (with EXAM_ABSENT_SUBJECT_FAILS on) fail every student
    in it. The column appears as soon as the first mark is entered.

    Deliberately scoped to the students of this exam: a mark left behind by a
    student who has since moved class must not keep a subject alive.
    """
    from .models import ExamMark

    if students is None:
        students = list(get_exam_students(exam, group=group))
    student_ids = [student.pk for student in students]
    if not student_ids:
        return set()
    return set(
        ExamMark.objects.filter(exam=exam, student_id__in=student_ids)
        .values_list('subject_id', flat=True).distinct()
    )


def unmarked_assigned_subjects(exam, group=None):
    """Assigned subjects this exam holds no mark for at all.

    :func:`build_exam_results` leaves these out of the printed register, so the
    result sheet can name them rather than silently printing a result with a
    subject missing from it. Covers both readings of "no marks": a subject
    assigned after the exam was published, and a subject whose marks the office
    has not entered yet.
    """
    students = list(get_exam_students(exam, group=group))
    assigned, _is_filtered = get_exam_subjects(exam, group=group)
    if not assigned:
        return []
    student_subject_ids = get_student_subject_ids(
        exam, students, subjects=assigned, group=group,
    )
    used_ids = set().union(*(ids for ids in student_subject_ids.values())) if students else set()
    assigned = [subject for subject in assigned if subject.pk in used_ids]
    marked = marked_subject_ids_for_exam(exam, students=students)
    return [subject for subject in assigned if subject.pk not in marked]


def build_exam_results(exam, group=None):
    """Compute every student's result for one exam.

    Returns (columns, results). The printed columns are the union of subjects
    assigned to at least one student during admission; only the main subjects
    each student actually takes count towards that student's total and GPA
    denominator. A selected ``FOURTH``-category paper remains visible and can
    add its points above 2.00 as the one approved fourth-subject bonus.

    A subject the exam holds **no mark for at all** is not a column (see
    :func:`marked_subject_ids_for_exam`): assignments are keyed to the class and
    read at result time, so a subject assigned after the exam was published must
    not arrive as an empty column and fail everyone. Individual absence still
    fails — a subject with marks for some students grades F for the ones with
    none. :func:`unmarked_assigned_subjects` lists what was left out so the
    result sheet can say so out loud.

    A result is only a Pass when the student passes every subject they sat
    individually; failing (or not sitting) one subject makes the whole result
    Fail with GPA 0.00, and the total-mark percentage and the class position
    are not counted for a failed result.

    The Islam and Hindu Religion & Moral Education papers are printed as one
    merged :class:`ReligionColumn` ('Religion', code REL): each student is
    graded on their own paper (Hindu students on Hindu, everyone else on
    Islam). A student whose own paper is not assigned gets a plain dash in that
    column — never a fail, never counted, and never an "absent subject".
    Papers that nobody in the class sits are not printed at all.
    """
    from .models import ExamMark

    students = list(get_exam_students(exam, group=group))
    assigned, _is_filtered = get_exam_subjects(exam, group=group)

    marks = {}
    for mark in ExamMark.objects.filter(exam=exam).select_related('student', 'subject'):
        marks.setdefault(mark.student_id, {})[mark.subject_id] = mark
    # A subject nobody in this exam has a mark for is not a column: see
    # marked_subject_ids_for_exam(). Without this, a subject assigned to the
    # class after the exam was published arrives as an empty column and fails
    # every student in it.
    marked_ids = marked_subject_ids_for_exam(exam, students=students)
    assigned = [subject for subject in assigned if subject.pk in marked_ids]

    student_subject_ids = get_student_subject_ids(
        exam, students, subjects=assigned, group=group,
    )
    used_ids = set().union(*(ids for ids in student_subject_ids.values()))
    assigned = [subject for subject in assigned if subject.pk in used_ids]

    # Papers no student in this exam sits (e.g. a Christian paper in a school
    # with no Christian students) drop out before the column is built.
    kept_subjects, religion_paper, religion_by_pk = applicable_religion_papers(
        exam, assigned, students,
    )
    used_paper_pks = {pk for pk in religion_paper.values() if pk is not None}
    used_religion_by_pk = {
        pk: label for pk, label in religion_by_pk.items() if pk in used_paper_pks
    }
    religion_column = None
    if used_religion_by_pk:
        papers_by_label = {
            label: next(subject for subject in kept_subjects if subject.pk == pk)
            for pk, label in used_religion_by_pk.items()
        }
        religion_column = ReligionColumn(papers_by_label, used_religion_by_pk)

    # Columns in subject order, with the single Religion column standing in for
    # the first of the merged papers.
    columns = []
    column_inserted = False
    for subject in kept_subjects:
        if subject.pk in used_religion_by_pk:
            if not column_inserted:
                columns.append(religion_column)
                column_inserted = True
            continue
        columns.append(subject)

    results = []
    for student in students:
        student_marks = marks.get(student.pk, {})
        subject_results = []
        # Totals, percentage and result status are based on the main papers.
        # A selected FOURTH-category paper remains visible in subject_results,
        # but contributes only its approved GPA bonus below.
        total_obtained = Decimal('0')
        total_full = Decimal('0')
        main_gpa_points = []
        fourth_subject_result = None
        has_fail = False

        for column in columns:
            selected_subject_ids = student_subject_ids.get(student.pk, set())
            if isinstance(column, ReligionColumn):
                paper = column.paper_for(student)
                if paper is None or paper.pk not in selected_subject_ids:
                    # This student's own religion paper is not assigned for
                    # the class: a plain dash, never counted and never a fail.
                    subject_results.append({
                        'subject': column, 'religion_column': True,
                        'not_applicable': True, 'absent': True,
                        'religion_unassigned': True,
                        'is_fourth_subject': False, 'counts_toward_result': False,
                        'obtained': None, 'full': None, 'percentage': None,
                        'grade': ABSENT, 'point': None, 'passed': False,
                        'failed_parts': [], 'parts': [], 'pass_marks': None,
                    })
                    continue
                marks_config = get_subject_marks(exam, paper, group=group)
                result = compute_subject_result(student_marks.get(paper.pk), marks_config)
                result['subject'] = column
                result['religion_column'] = True
                result['paper'] = paper
            else:
                if column.pk not in selected_subject_ids:
                    # Optional subjects are columns shared by the class, but a
                    # student who did not select one gets a blank, never an
                    # absent/fail result and never a total/GPA contribution.
                    subject_results.append({
                        'subject': column, 'subject_unassigned': True,
                        'not_applicable': True, 'absent': True,
                        'is_fourth_subject': column.category == 'FOURTH',
                        'counts_toward_result': column.category != 'FOURTH',
                        'obtained': None, 'full': None, 'percentage': None,
                        'grade': ABSENT, 'point': None, 'passed': False,
                        'failed_parts': [], 'parts': [], 'pass_marks': None,
                    })
                    continue
                marks_config = get_subject_marks(exam, column, group=group)
                result = compute_subject_result(student_marks.get(column.pk), marks_config)
                result['subject'] = column

            is_fourth_subject = (
                not isinstance(column, ReligionColumn)
                and getattr(column, 'category', None) == 'FOURTH'
            )
            result['is_fourth_subject'] = is_fourth_subject
            result['counts_toward_result'] = not is_fourth_subject
            if is_fourth_subject:
                # Publishing prevents more than one selected FOURTH paper.  If
                # legacy/unpublished data reaches this path anyway, retain the
                # first applicable paper rather than awarding an accidental
                # double bonus. An unselected optional paper is not a fourth
                # subject for that student at all.
                if not result.get('not_applicable'):
                    fourth_subject_result = fourth_subject_result or result
            else:
                counted = not result['absent'] or result['obtained'] is not None
                if counted:
                    # An absent main subject arrives here as 0 / Full Marks and
                    # fails the result. A fourth-subject AB/F is deliberately
                    # outside this branch and only earns zero bonus.
                    total_obtained += result['obtained']
                    total_full += Decimal(str(result['full']))
                    has_fail = has_fail or not result['passed']
                    main_gpa_points.append(result['point'])
            subject_results.append(result)

        attempted = [
            row for row in subject_results
            if not row['is_fourth_subject'] and not row['absent']
        ]
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
            fourth_subject_point = (
                fourth_subject_result['point'] if fourth_subject_result is not None else None
            )
            overall_gpa = calculate_final_gpa(main_gpa_points, fourth_subject_point)
            overall_grade, _ = get_grade(float(overall_percentage))
            status = 'Pass'
            # A fourth-subject bonus may reach the statutory cap even when the
            # main-paper percentage alone is below 80. GPA 5.00 is published as
            # A+ consistently in that case.
            if overall_gpa == GPA_MAXIMUM:
                overall_grade = 'A+'

        results.append({
            'student': student, 'subject_results': subject_results,
            'total_obtained': total_obtained, 'total_full': total_full,
            'percentage': round(float(overall_percentage), 2) if overall_percentage is not None else None,
            'gpa': overall_gpa,
            'fourth_subject_point': (
                fourth_subject_result['point'] if fourth_subject_result is not None else None
            ),
            'main_subject_count': len(main_gpa_points),
            'grade': overall_grade, 'status': status,
            # "has marks" means there is something to print: a student whose only
            # rows sit in subjects outside this exam still counts as No Marks.
            'has_marks': bool(attempted),
            'absent_subject_count': sum(
                1 for r in subject_results
                if r['absent'] and not r.get('not_applicable')
                and not r.get('religion_unassigned')
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
    return columns, ranked + [result for result in results if result['position'] is None]


def failed_subject_rows(exam, group=None):
    """Return one row for every failed applicable subject in an exam.

    The function uses :func:`build_exam_results`, so optional/religion papers,
    part-pass rules and institution/class scope are identical to published
    result sheets. Completely missing mandatory papers count as failures;
    optional papers a student did not choose do not.
    """
    _columns, results = build_exam_results(exam, group=group)
    rows = []
    for result in results:
        for subject_result in result['subject_results']:
            if subject_result.get('not_applicable'):
                continue
            if subject_result.get('passed'):
                continue
            subject = subject_result.get('paper') or subject_result.get('subject')
            rows.append({
                'exam': exam,
                'student': result['student'],
                'subject': subject,
                'obtained': subject_result.get('obtained'),
                'full': subject_result.get('full'),
                'grade': subject_result.get('grade'),
                'absent': subject_result.get('absent', False),
                'failed_parts': subject_result.get('failed_parts', []),
                'result': subject_result,
            })
    return sorted(rows, key=lambda row: (
        getattr(row['subject'], 'code', ''),
        row['student'].roll_no is None,
        row['student'].roll_no or 0,
        row['student'].name.lower(),
        row['student'].pk,
    ))


def section_arrangement_rows(exam, group=None):
    """Rank all candidates for merit-based section arrangement.

    Fewer failed subjects always comes first; ties are decided by higher total
    marks, then the existing roll, name and pk for deterministic previews.
    This ranking intentionally does not use or alter ``roll_no``.
    """
    _columns, results = build_exam_results(exam, group=group)
    rows = []
    for result in results:
        failed_count = sum(
            1 for subject_result in result['subject_results']
            if not subject_result.get('not_applicable')
            and not subject_result.get('passed')
        )
        row = dict(result)
        row.update({
            'failed_subject_count': failed_count,
            'current_section': result['student'].section,
            'proposed_section': result['student'].section,
        })
        rows.append(row)
    return sorted(rows, key=lambda row: (
        row['failed_subject_count'],
        -row['total_obtained'],
        row['student'].roll_no is None,
        row['student'].roll_no or 0,
        row['student'].name.lower(),
        row['student'].pk,
    ))
