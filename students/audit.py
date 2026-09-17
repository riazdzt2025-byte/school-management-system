from .models import AuditLog


def _audit_institution_for(instance):
    """Best-effort Institution an audited object belongs to.

    A row on the student roll is read-side isolated per institution, so its
    audit trail must be too: a clerk bound to school A must not read school
    B's archive/publish/payment history just because they hold view_auditlog.
    Returns ``None`` when there is no instance (system-level action) or the
    object carries no institution — such rows stay visible to admin/staff
    only (deny-by-default, the same rule null-institution vouchers follow).

    Model *classes* are accepted: the attendance views audit an aggregate
    action as ``record_audit(user, 'attendance_marked', Student, ...)`` with
    no concrete row behind it.
    """
    if instance is None or isinstance(instance, type):
        return None
    institution = getattr(instance, 'institution', None)
    if institution is not None:
        return institution
    # Receipts, certificates and TCs belong to a student; salary sheets to an
    # employee — resolve the institution through that link.
    for link in ('student', 'employee'):
        related = getattr(instance, link, None)
        if related is not None:
            return getattr(related, 'institution', None)
    return None


def record_audit(actor, action, instance=None, snapshot=None, details=None, model_name=None, object_id=''):
    institution = _audit_institution_for(instance)
    if instance is not None:
        model = instance._meta
        model_name = model_name or model.label
        if isinstance(instance, type):
            # A model class (not a row) was passed for an aggregate action:
            # there is no pk, so object_id must not end up as the string of
            # the `pk` property object.
            object_repr = model.verbose_name
        else:
            object_id = str(instance.pk)
            object_repr = str(instance)
    else:
        object_repr = ''
    return AuditLog.objects.create(
        actor=actor if getattr(actor, 'is_authenticated', False) else None,
        action=action,
        model_name=model_name or '',
        object_id=object_id,
        object_repr=object_repr,
        institution=institution,
        snapshot=snapshot or {},
        details=details or {},
    )
