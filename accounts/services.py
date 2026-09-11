from django.db import transaction

from audit import services as audit
from audit.models import AuditAction

from .models import User


@transaction.atomic
def update_own_mobile(*, user, mobile, request=None):
    """
    Set the user's own mobile number and record that it changed.

    Invariant: only the `mobile` column is written; no other field of the
    user record can change through this path. The number itself is not
    copied into the audit log.
    """
    previous = User.objects.filter(pk=user.pk).values_list("mobile", flat=True).get()
    user.mobile = mobile
    user.save(update_fields=["mobile"])
    if previous != mobile:
        audit.log(
            action=AuditAction.PROFILE_UPDATED,
            actor=user,
            obj=user,
            summary=f"{user.full_name} updated their mobile number",
            detail={"fields": ["mobile"]},
            request=request,
        )
    return user
