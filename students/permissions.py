from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType


def _group_permission_map():
    from .models import (
        AdmissionApplication,
        AuditLog,
        Certificate,
        Employee,
        EmployeeStatusLog,
        Exam,
        ExamMark,
        MoneyReceipt,
        PromotionBatch,
        SeatPlan,
        Student,
        StudentPromotionHistory,
        Subject,
        SubjectRequirement,
        TransferCertificate,
        Voucher,
        SalarySheet,
    )

    return {
        'Admission': [
            (AdmissionApplication, ['add', 'change', 'view']),
            (Student, ['add', 'change', 'delete', 'view']),
            (TransferCertificate, ['add', 'change', 'delete']),
            (Certificate, ['add', 'change', 'delete']),
            (PromotionBatch, ['add', 'change', 'view']),
            (StudentPromotionHistory, ['add', 'view']),
        ],
        'Office': [
            (AdmissionApplication, ['add', 'change', 'view']),
            # 'view' matters: the Archive page is guarded by
            # students.view_student, and without it the department that does
            # the archiving gets 403 on the only page that lists what it
            # archived.
            (Student, ['add', 'change', 'delete', 'view']),
            (TransferCertificate, ['add', 'change', 'delete']),
            (Certificate, ['add', 'change', 'delete']),
            (PromotionBatch, ['add', 'change', 'view']),
            (StudentPromotionHistory, ['add', 'view']),
            # Subject Assignment (বিষয় নির্ধারণ) is an Office workflow: the
            # list page is guarded by students.view_subjectrequirement and the
            # add/edit/delete/auto-fill actions by the matching write perms,
            # all scoped to the user's institutions in the views/forms.
            (SubjectRequirement, ['add', 'change', 'delete', 'view']),
            # The Assign Subject form creates a brand-new Subject inline ("or
            # add a new subject below"), so the department that assigns
            # subjects has to be able to create them — otherwise the workflow
            # stops at a form field the user is not allowed to use.
            # 'change' is what the Mark Evaluation page is guarded by
            # (students.change_subject); without it the office that set the
            # curriculum could not set Full Marks / CQ / MCQ / pass % for it.
            # No 'delete': removing a Subject orphans the ExamMarks already
            # entered against it, so that stays with the Subjects group.
            (Subject, ['add', 'change']),
        ],
        'Subjects': [
            (Subject, ['add', 'change', 'delete']),
            # Read access to the assignment list (it used to be login-only);
            # Subjects users manage the subject master and may inspect where
            # subjects are assigned. No write access to assignments.
            (SubjectRequirement, ['view']),
        ],
        'Exam': [
            (Student, ['view']),
            (Exam, ['add', 'change']),
            (ExamMark, ['add', 'change', 'delete']),
            (SeatPlan, ['add', 'change', 'delete']),
            # Read-only: the Enter Marks / Import / Result Sheet pages point
            # at the Subject Assignments list when a class has no subjects
            # yet ("Go to Subject Assignments"), so Exam keeps the read view
            # and gains no write access.
            (SubjectRequirement, ['view']),
            # Mark Evaluation (নম্বর বণ্টন) is per Institution + Class + Exam
            # Type, i.e. exactly the exam department's job: it decides Full
            # Marks / CQ / MCQ / Practical / pass % and which subjects count.
            # The page is guarded by students.change_subject, so without this
            # the sidebar link every Exam user sees led straight to a 403.
            (Subject, ['change']),
        ],
        'HR': [
            (Employee, ['add', 'change', 'delete']),
            (EmployeeStatusLog, ['add', 'view']),
        ],
        'Accounts': [
            (Student, ['view']),
            (AdmissionApplication, ['change', 'view']),
            (MoneyReceipt, ['add', 'change', 'delete']),
            (Voucher, ['add', 'change', 'delete']),
            (SalarySheet, ['add', 'change', 'delete']),
            (Exam, ['add', 'change']),
            (ExamMark, ['add', 'change', 'delete']),
            # Read-only: Accounts also enters marks, so its "Go to Subject
            # Assignments" workflow links keep working.
            (SubjectRequirement, ['view']),
        ],
        'Audit': [
            (AuditLog, ['view']),
        ],
    }


def ensure_default_groups():
    """Create the default department groups and ensure each includes the correct permissions."""
    for group_name, model_permissions in _group_permission_map().items():
        group, _ = Group.objects.get_or_create(name=group_name)
        group.permissions.clear()

        for model, actions in model_permissions:
            content_type = ContentType.objects.get_for_model(model)
            for action in actions:
                codename = f'{action}_{model._meta.model_name}'
                permission = Permission.objects.filter(content_type=content_type, codename=codename).first()
                if permission:
                    group.permissions.add(permission)

        group.save()

    return list(_group_permission_map().keys())


def sync_user_department_permissions(user):
    """Mirror the user's active institution access into Django groups.

    Intentional limit (SEC-FU-2): a non-admin clerk signs in through one of the
    three login departments (Office, Exam, Accounts), so only those access rows
    are mirrored (Office also brings Admission). Membership of the HR, Subjects
    and Audit groups is never granted here and is removed at the next login.
    Admin/staff accounts are skipped and may use those groups directly. See
    students/test_department_group_sync.py.
    """
    if user is None or getattr(user, 'is_anonymous', True):
        return

    if user.is_superuser or user.is_staff:
        return

    from .models import InstitutionAccess

    department_aliases = {
        'Office': {'Office', 'Admission'},
        'Exam': {'Exam'},
        'Accounts': {'Accounts'},
    }

    desired_group_names = set()
    for access in InstitutionAccess.objects.filter(user=user, is_active=True):
        for source, targets in department_aliases.items():
            if access.department == source:
                desired_group_names.update(targets)
                break

    for group_name in ['Office', 'Admission', 'Subjects', 'Exam', 'HR', 'Accounts', 'Audit']:
        group = Group.objects.filter(name=group_name).first()
        if not group:
            continue
        if group_name in desired_group_names:
            user.groups.add(group)
        else:
            user.groups.remove(group)
