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
        SSCRegistration,
        Student,
        StudentPromotionHistory,
        Subject,
        TransferCertificate,
        Voucher,
        SalarySheet,
        BoardResult,
    )

    return {
        'Admission': [
            (AdmissionApplication, ['add', 'change', 'view']),
            (Student, ['add', 'change', 'delete']),
            (TransferCertificate, ['add', 'change', 'delete']),
            (Certificate, ['add', 'change', 'delete']),
            (PromotionBatch, ['add', 'change', 'view']),
            (StudentPromotionHistory, ['add', 'view']),
        ],
        'Office': [
            (AdmissionApplication, ['add', 'change', 'view']),
            (Student, ['add', 'change', 'delete']),
            (TransferCertificate, ['add', 'change', 'delete']),
            (Certificate, ['add', 'change', 'delete']),
            (PromotionBatch, ['add', 'change', 'view']),
            (StudentPromotionHistory, ['add', 'view']),
        ],
        'Subjects': [
            (Subject, ['add', 'change', 'delete']),
        ],
        'Exam': [
            (SSCRegistration, ['add', 'change', 'delete']),
            (BoardResult, ['add', 'change', 'delete']),
            (Exam, ['add', 'change', 'delete']),
            (ExamMark, ['add', 'change', 'delete']),
            (SeatPlan, ['add', 'change', 'delete']),
        ],
        'HR': [
            (Employee, ['add', 'change', 'delete']),
            (EmployeeStatusLog, ['add', 'view']),
        ],
        'Accounts': [
            (AdmissionApplication, ['change', 'view']),
            (MoneyReceipt, ['add', 'change', 'delete']),
            (Voucher, ['add', 'change', 'delete']),
            (SalarySheet, ['add', 'change', 'delete']),
            (Exam, ['add', 'change', 'delete']),
            (ExamMark, ['add', 'change', 'delete']),
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
    """Mirror the user's active institution access into Django groups."""
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
