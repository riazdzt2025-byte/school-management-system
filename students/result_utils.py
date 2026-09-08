"""Marking rules shared by every exam route.

Marks entry, Excel import, seat planning and the result pages must agree on two
things or the school ends up with a different set of students/subjects per
screen: who belongs to an exam, and how a mark turns into a grade. Both live
here so there is exactly one implementation of each.
"""
from collections import defaultdict
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
    subject_ids = list(active_exam_subject_ids(exam, subject_ids))
    if not subject_ids:
        return [], True
    # The printed register follows the examination subject serial/code
    # (101, 102, 107, 108, 136, 150 in the school's result format), not
    # alphabetical subject names. This keeps marks entry, imports and the
    # result sheet in the same predictable order.
    return list(Subject.objects.filter(pk__in=subject_ids).order_by('code', 'name')), True


def active_exam_subject_ids(exam, subject_ids):
    """Subject ids still enabled in Mark Evaluation for this exam type.

    Mark Evaluation has an Active/Count checkbox per Institution + Class +
    Subject + Exam Type. A missing row means the subject remains active so old
    data behaves exactly as before; only an explicit unchecked setting disables
    a subject for marks entry/import/result calculation.
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

    preferred_class = str(admission_class).strip()
    class_variants = class_filter_variants(preferred_class)
    class_rank = {preferred_class: 0}
    for value in class_variants:
        class_rank.setdefault(value, len(class_rank))

    settings = SubjectMarkSetting.objects.filter(
        institution_id=institution_id,
        admission_class__in=class_variants,
        subject_id__in=subject_ids,
        exam_type=exam_type,
    ).values('subject_id', 'admission_class', 'is_active')

    active_by_subject = {}
    for row in sorted(settings, key=lambda item: class_rank.get(item['admission_class'], 99)):
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

    def header_marks_config(self, exam):
        """Full Marks for the column header: prefer the Islam paper's exam
        setting, then any other assigned paper — the papers share the same
        marks structure in every real curriculum."""
        paper = (
            self.paper_for_label('Islam')
            or next(iter(self.papers_by_label.values()), None)
        )
        return get_subject_marks(exam, paper) if paper else None

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


def build_exam_results(exam, group=None):
    """Compute every student's result for one exam.

    Returns (columns, results). The printed columns are the union of subjects
    assigned to at least one student during admission; only the subjects each
    student actually takes count towards that student's total and GPA.

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
                        'obtained': None, 'full': None, 'percentage': None,
                        'grade': ABSENT, 'point': None, 'passed': False,
                        'failed_parts': [], 'parts': [], 'pass_marks': None,
                    })
                    continue
                marks_config = get_subject_marks(exam, paper)
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
                        'obtained': None, 'full': None, 'percentage': None,
                        'grade': ABSENT, 'point': None, 'passed': False,
                        'failed_parts': [], 'parts': [], 'pass_marks': None,
                    })
                    continue
                marks_config = get_subject_marks(exam, column)
                result = compute_subject_result(student_marks.get(column.pk), marks_config)
                result['subject'] = column

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
