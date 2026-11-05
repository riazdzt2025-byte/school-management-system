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
        for index, result in enumerate(members):
            result['special_rank'] = rank_cursor + index if has_manual_order else rank_cursor
            result['subject_marks'] = [
                subject_result.get('obtained')
                if not subject_result.get('not_applicable') else None
                for subject_result in result['subject_results']
            ]
            result['result_percentage'] = (
                Decimal(result['total_obtained']) * 100 / Decimal(result['total_full'])
                if result['total_full'] else None
            )
            result['result_status'] = (
                'No Marks' if result['result_percentage'] is None
                else 'Pass' if result['result_percentage'] >= 40
                else 'Fail'
            )
            ordered_rows.append(result)
            group_members.append(result)
        if len(members) > 1:
            tie_groups.append({
                'total_marks': total,
                'members': group_members,
                'student_ids': ','.join(str(row['student'].pk) for row in group_members),
                'has_manual_order': has_manual_order,
            })
        rank_cursor += len(members)

    for result in sorted(unmarked_candidates, key=_register_order):
        result['special_rank'] = None
        result['subject_marks'] = [
            subject_result.get('obtained')
            if not subject_result.get('not_applicable') else None
            for subject_result in result['subject_results']
        ]
        result['result_percentage'] = None
        result['result_status'] = 'No Marks'
        ordered_rows.append(result)

    if order == 'merit':
        ordered_rows.sort(key=lambda row: (
            row['special_rank'] is None,
            row['special_rank'] if row['special_rank'] is not None else 0,
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
