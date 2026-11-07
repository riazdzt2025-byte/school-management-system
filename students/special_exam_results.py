"""Total-marks result rows for the optional Special Exam report."""
from collections import defaultdict
from decimal import Decimal

from .result_utils import build_exam_results


def _register_order(result):
    student = result['student']
    return (
        student.roll_no is None,
        student.roll_no if student.roll_no is not None else 0,
        student.name.casefold(),
        student.pk,
    )


def _set_subject_report_marks(result):
    """Prepare visible marks, failures and A+ count from subject calculations."""
    subject_mark_details = []
    for subject_result in result['subject_results']:
        has_mark = (
            not subject_result.get('not_applicable')
            and not subject_result.get('absent')
            and not subject_result.get('pending')
            and subject_result.get('obtained') is not None
        )
        subject_mark_details.append({
            'mark': subject_result.get('obtained') if has_mark else None,
            'failed': has_mark and subject_result.get('grade') == 'F',
        })

    result['subject_mark_details'] = subject_mark_details
    result['subject_marks'] = [
        detail['mark'] for detail in subject_mark_details
    ]
    result['a_plus_count'] = sum(
        1 for subject_result in result['subject_results']
        if not subject_result.get('not_applicable')
        and not subject_result.get('absent')
        and not subject_result.get('pending')
        and subject_result.get('grade') == 'A+'
    )


def build_special_exam_result(exam, group=None, order='roll'):
    """Build the live total-marks report and its editable equal-total groups.

    The normal exam result applies GPA/pass ranking rules. This separate report
    uses the existing per-student subject calculations, but calculates merit
    by raw total marks. Saved tie orders are used only when their student set
    still exactly matches the current equal-total set for this selected group.
    Rows are returned in register order unless merit order is requested.
    """
    from .models import SpecialExamRankOrder

    columns, results = build_exam_results(exam, group=group)
    ranked_candidates = [row for row in results if row['has_marks']]
    unmarked_candidates = [row for row in results if not row['has_marks']]
    effective_group = (group if group is not None else exam.group) or ''

    by_total = defaultdict(list)
    for result in ranked_candidates:
        by_total[Decimal(result['total_obtained'])].append(result)

    ordered_rows = []
    tie_groups = []
    rank_cursor = 1
    serial_cursor = 1
    for total in sorted(by_total, reverse=True):
        members = by_total[total]
        saved = list(
            SpecialExamRankOrder.objects.filter(
                exam=exam, group=effective_group, total_marks=total,
            ).order_by('order').values_list('student_id', flat=True)
        )
        member_ids = {row['student'].pk for row in members}
        has_manual_order = len(members) > 1 and set(saved) == member_ids and len(saved) == len(members)
        if has_manual_order:
            order_by_id = {student_id: index for index, student_id in enumerate(saved)}
            members.sort(key=lambda row: order_by_id[row['student'].pk])
        else:
            members.sort(key=_register_order)

        group_members = []
        passed_index = 0
        for index, result in enumerate(members):
            result['special_serial'] = serial_cursor + index
            if result['status'] == 'Pass':
                result['special_rank'] = (
                    rank_cursor + passed_index if has_manual_order else rank_cursor
                )
                passed_index += 1
            else:
                result['special_rank'] = 0
            _set_subject_report_marks(result)
            ordered_rows.append(result)
            group_members.append(result)
        if len(members) > 1:
            tie_groups.append({
                'total_marks': total,
                'members': group_members,
                'student_ids': ','.join(str(row['student'].pk) for row in group_members),
                'has_manual_order': has_manual_order,
            })
        rank_cursor += passed_index
        serial_cursor += len(members)

    for result in sorted(unmarked_candidates, key=_register_order):
        result['special_rank'] = None
        result['special_serial'] = None
        _set_subject_report_marks(result)
        ordered_rows.append(result)

    if order == 'merit':
        ordered_rows.sort(key=lambda row: (
            row['special_serial'] is None,
            row['special_rank'] == 0,
            row['special_serial'] if row['special_serial'] is not None else 0,
            _register_order(row),
        ))
    else:
        ordered_rows.sort(key=_register_order)

    return {
        'columns': columns,
        'results': ordered_rows,
        'tie_groups': tie_groups,
        'effective_group': effective_group,
        'order': 'merit' if order == 'merit' else 'roll',
    }
