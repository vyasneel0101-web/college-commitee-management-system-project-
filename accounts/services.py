from django.conf import settings
from django.db import transaction

from audit import services as audit
from audit.models import AuditAction

from .models import Role, User


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


@transaction.atomic
def create_faculty(*, created_by, request=None, **fields):
    """
    Add a staff record. Always created as FACULTY: no caller can set a role
    through this path, and the Principal's role is changed only in the admin.

    Under DEMO_MODE the demonstration password is set so the account can be
    shown working; otherwise the account has no usable password until
    magic-link sign-in exists (debt item 3).
    """
    user = User(created_by=created_by, **fields)
    user.role = Role.FACULTY
    user.is_staff = False
    user.is_superuser = False
    if settings.DEMO_MODE:
        user.set_password("demo1234")
    else:
        user.set_unusable_password()
    user.full_clean(exclude=["password"])
    user.save()
    audit.log(
        action=AuditAction.FACULTY_CREATED,
        actor=created_by,
        obj=user,
        summary=f"{user.full_name} added as faculty",
        detail={"email": user.email, "designation": user.designation},
        request=request,
    )
    return user


@transaction.atomic
def update_faculty(*, user, actor, changed_fields, request=None):
    """Correct a staff record. Role and active status are not writable here."""
    user.save(update_fields=list(changed_fields))
    audit.log(
        action=AuditAction.FACULTY_UPDATED,
        actor=actor,
        obj=user,
        summary=f"{user.full_name}: record corrected",
        detail={"fields": sorted(changed_fields)},
        request=request,
    )
    return user


@transaction.atomic
def deactivate_faculty(*, user, actor, request=None):
    """
    Stop someone signing in, keeping all their history (BR-9).

    Invariant: active assignments are NOT ended by this. They must be
    relinquished by order, so the caller is warned first and the committee
    record stays truthful.
    """
    user.is_active = False
    user.save(update_fields=["is_active"])
    audit.log(
        action=AuditAction.FACULTY_DEACTIVATED,
        actor=actor,
        obj=user,
        summary=f"{user.full_name} deactivated",
        detail={"active_assignments": user.assignments.filter(status="ACTIVE").count()},
        request=request,
    )
    return user
