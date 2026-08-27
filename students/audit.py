from .models import AuditLog


def record_audit(actor, action, instance=None, snapshot=None, details=None, model_name=None, object_id=''):
    if instance is not None:
        model = instance._meta
        model_name = model_name or model.label
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
        snapshot=snapshot or {},
        details=details or {},
    )