from .models import AuditLogEntry


def log(*, action, summary, obj=None, actor=None, detail=None, request=None):
    """
    Append one entry to the audit log.

    Invariant: entries are only ever created, never updated or deleted.
    `detail` holds changed field names and values only, never a document or
    a secret.
    """
    request_user = getattr(request, "user", None)
    if actor is None and request_user is not None and request_user.is_authenticated:
        actor = request_user
    return AuditLogEntry.objects.create(
        actor=actor,
        action=action,
        object_type=obj._meta.label if obj is not None else "",
        object_id=str(obj.pk) if obj is not None else "",
        summary=summary[:255],
        detail=detail or {},
        ip_address=request.META.get("REMOTE_ADDR") if request is not None else None,
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:300] if request is not None else "",
    )
