from decimal import Decimal


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
def get_subject_marks(exam, subject):
    """
    Returns an object with full_marks / cq_marks / mcq_marks / pass_marks /
    has_cq_mcq_split for this exam+subject combination — using the specific
    SubjectMarkSetting if one exists, otherwise falling back to the subject's
    own global defaults.
    """
    from .models import SubjectMarkSetting

    setting = SubjectMarkSetting.objects.filter(
        institution=exam.institution,
        admission_class=exam.admission_class,
        subject=subject,
        exam_type=exam.exam_type,
    ).first()

    return setting if setting else subject

def build_exam_results(exam):
    from .models import ExamMark, Student, Subject

    students = Student.objects.filter(admission_class=exam.admission_class)
    if exam.section:
        students = students.filter(section__iexact=exam.section.strip())
    students = students.order_by('roll_no', 'name')

    marks = ExamMark.objects.filter(exam=exam).select_related('student', 'subject')
    subjects = Subject.objects.filter(
        id__in=marks.values_list('subject_id', flat=True).distinct()
    ).order_by('name')
    marks_map = {}
    for mark in marks:
        marks_map.setdefault(mark.student_id, {})[mark.subject_id] = mark

    results = []
    for student in students:
        student_marks = marks_map.get(student.pk, {})
        subject_results = []
        total_obtained = Decimal('0')
        total_full = Decimal('0')
        gpa_points = []
        has_fail = False

        for subject in subjects:
            mark = student_marks.get(subject.pk)
            obtained = mark.marks_obtained if mark else Decimal('0')
            marks_config = get_subject_marks(exam, subject)
            full = Decimal(str(marks_config.full_marks))
            percentage = (obtained / full * 100) if full else Decimal('0')
            grade, point = get_grade(float(percentage))
            subject_pass_marks = Decimal(str(marks_config.pass_marks))
            subject_passed = obtained >= subject_pass_marks
            has_fail = has_fail or not subject_passed
            total_obtained += obtained
            total_full += full
            gpa_points.append(point)
            subject_results.append({
                'subject': subject, 'obtained': obtained, 'full': marks_config.full_marks,
                'percentage': round(float(percentage), 2), 'grade': grade, 'point': point,
                'passed': subject_passed, 'pass_marks': marks_config.pass_marks,
            })

        overall_percentage = (total_obtained / total_full * 100) if total_full else Decimal('0')
        if not student_marks:
            overall_gpa, overall_grade, status = None, '-', 'No Marks'
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
            'grade': overall_grade, 'status': status, 'has_marks': bool(student_marks),
            'position': None,
        })

    ranked = sorted(
        (result for result in results if result['has_marks']),
        key=lambda result: (-result['gpa'], -result['total_obtained'])
    )
    previous_key = None
    for index, result in enumerate(ranked):
        key = (result['gpa'], result['total_obtained'])
        result['position'] = ranked[index - 1]['position'] if index and key == previous_key else index + 1
        previous_key = key
    return subjects, ranked + [result for result in results if not result['has_marks']]
