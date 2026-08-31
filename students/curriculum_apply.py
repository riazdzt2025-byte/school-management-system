"""Apply the built-in Bangladesh-curriculum defaults (see curriculum_data.py)
to a specific Institution + Class, creating Subject and SubjectRequirement
rows as needed. Safe to re-run — existing rows are left untouched, so an
admin's manual edits are never overwritten."""

from .models import Subject, SubjectRequirement
from .curriculum_data import SUBJECTS, curriculum_for_class

_SUBJECT_LOOKUP = {code: (name, full_marks, category) for code, name, full_marks, category in SUBJECTS}


def _get_or_create_subject(code):
    if code not in _SUBJECT_LOOKUP:
        return None
    name, full_marks, category = _SUBJECT_LOOKUP[code]
    subject, _ = Subject.objects.get_or_create(
        code=code, defaults={'name': name, 'full_marks': full_marks, 'category': category},
    )
    return subject


def _apply_rows(institution, admission_class, group, rows):
    created = 0
    for code, req_type, opt_key, condition_religion in rows:
        subject = _get_or_create_subject(code)
        if subject is None:
            continue
        _, was_created = SubjectRequirement.objects.get_or_create(
            institution=institution,
            admission_class=admission_class,
            group=group,
            subject=subject,
            defaults={
                'requirement_type': req_type,
                'optional_set_key': opt_key,
                'condition_religion': condition_religion,
            },
        )
        if was_created:
            created += 1
    return created


def apply_curriculum(institution, admission_class, group=''):
    """Create the default SubjectRequirement rows for this Institution +
    Class (+ Group, if given). Returns the number of rows created.
    Returns None if this class isn't covered by the built-in curriculum
    (e.g. a diploma semester) so the caller can tell the user to add rows
    manually instead."""
    common_rows, group_rows = curriculum_for_class(admission_class)
    if common_rows is None:
        return None

    created = _apply_rows(institution, admission_class, '', common_rows)
    if group and group in group_rows:
        created += _apply_rows(institution, admission_class, group, group_rows[group])
    elif not group:
        for group_code, rows in group_rows.items():
            created += _apply_rows(institution, admission_class, group_code, rows)
    return created
