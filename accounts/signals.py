from django.contrib.auth.signals import user_logged_in, user_login_failed
from django.dispatch import receiver

from audit import services as audit
from audit.models import AuditAction


@receiver(user_logged_in)
def record_sign_in(sender, request, user, **kwargs):
    audit.log(
        action=AuditAction.LOGIN_SUCCESS,
        actor=user,
        obj=user,
        summary=f"{user.full_name or user.email} signed in",
        request=request,
    )


@receiver(user_login_failed)
def record_failed_sign_in(sender, credentials, request=None, **kwargs):
    # Django masks the password in `credentials`; only the typed email is kept.
    audit.log(
        action=AuditAction.LOGIN_FAILED,
        summary="Failed sign-in attempt",
        detail={"username": str(credentials.get("username", ""))[:254]},
        request=request,
    )
