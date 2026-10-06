"""
The assignment state machine. docs/02_DATA_MODEL.md, BR-2, BR-3, BR-8.

Every status transition happens here and nowhere else. No function in this
module deletes a row.
"""

from django.db import transaction
from django.utils.translation import gettext as _

from audit import services as audit
from audit.models import AuditAction
from core.exceptions import (
    AssignmentConflict,
    AssignmentNotActive,
    CommitteeInactive,
    FacultyInactive,
    OrderDateInvalid,
    RestoreBlocked,
    RoleNotAllowed,
)

from .models import Assignment, AssignmentRole, AssignmentStatus


def current_convener(committee):
    """The committee's ACTIVE convener assignment, or None."""
    return (
        Assignment.objects.active()
        .select_related("faculty")
        .filter(committee=committee, role=AssignmentRole.CONVENER)
        .first()
    )


def validate_assignment(*, faculty, committee, role, order_date):
    """
    Raise a DomainError if this assignment cannot be made. Writes nothing.

    Called before an order number is consumed, and again inside
    assign_committee, so the rules hold whichever entry point is used.
    """
    if not committee.is_active:
        raise CommitteeInactive()
    if not faculty.is_active:
        raise FacultyInactive()
    if role == AssignmentRole.MEMBER and not committee.allows_multiple_members:
        raise RoleNotAllowed()
    if (
        Assignment.objects.active()
        .filter(faculty=faculty, committee=committee, role=role)
        .exists()
    ):
        raise AssignmentConflict()
    if role == AssignmentRole.CONVENER:
        holder = current_convener(committee)
        # The holder's end_date becomes this order's date, so it cannot precede their start.
        if holder is not None and order_date < holder.start_date:
            raise OrderDateInvalid(
                _(
                    "The order date is before %(name)s became convener on %(date)s. "
                    "Choose a later date."
                )
                % {"name": holder.faculty.full_name, "date": holder.start_date.strftime("%d-%m-%Y")}
            )


@transaction.atomic
def assign_committee(*, faculty, committee, role, order, effective_date=None):
    """
    Create an ACTIVE assignment issued by `order`.

    Invariants maintained (BR-2, BR-3, BR-8):
    - at most one ACTIVE convener per committee: assigning a convener
      supersedes the current one, whose end_date becomes the new order's date,
      whose ending_order is `order`, and whose superseded_by is the new row;
    - adding a member leaves every other assignment untouched;
    - a faculty member never holds the same ACTIVE role twice in a committee;
    - all of it happens or none of it does. Nothing is deleted.
    """
    start_date = effective_date or order.order_date
    validate_assignment(
        faculty=faculty, committee=committee, role=role, order_date=order.order_date
    )

    previous = None
    if role == AssignmentRole.CONVENER:
        previous = (
            Assignment.objects.active()
            .select_for_update()
            .filter(committee=committee, role=AssignmentRole.CONVENER)
            .first()
        )
        if previous is not None:
            # Must end before the new row is inserted: uniq_active_convener.
            previous.status = AssignmentStatus.SUPERSEDED
            previous.end_date = order.order_date
            previous.ending_order = order
            previous.save(update_fields=["status", "end_date", "ending_order"])

    assignment = Assignment.objects.create(
        faculty=faculty,
        committee=committee,
        role=role,
        academic_year=order.academic_year,
        status=AssignmentStatus.ACTIVE,
        start_date=start_date,
        issuing_order=order,
    )
    audit.log(
        action=AuditAction.ASSIGNMENT_CREATED,
        actor=order.issued_by,
        obj=assignment,
        summary=f"{faculty.full_name} assigned {assignment.get_role_display()} of {committee.code} by {order.order_no}",
        detail={"order_no": order.order_no, "role": role, "start_date": start_date.isoformat()},
    )

    if previous is not None:
        previous.superseded_by = assignment
        previous.save(update_fields=["superseded_by"])
        audit.log(
            action=AuditAction.ASSIGNMENT_SUPERSEDED,
            actor=order.issued_by,
            obj=previous,
            summary=f"{previous.faculty.full_name} superseded as {previous.get_role_display()} of {committee.code} by {order.order_no}",
            detail={"superseded_by": assignment.pk, "end_date": order.order_date.isoformat()},
        )
    return assignment


@transaction.atomic
def expire_assignments_for_year(academic_year, *, carry_forward=()):
    """
    Year-end rollover: ACTIVE assignments of `academic_year` become EXPIRED,
    with end_date set to the year's end date.

    Assignments listed in `carry_forward` stay ACTIVE into the next year (a
    standing appointment continues until an order replaces it). Rows of other
    years and non-ACTIVE rows are untouched. Returns the number expired.
    """
    keep = [assignment.pk for assignment in carry_forward]
    expiring = (
        Assignment.objects.active()
        .select_for_update()
        .select_related("faculty", "committee")
        .filter(academic_year=academic_year)
        .exclude(pk__in=keep)
    )
    count = 0
    for assignment in expiring:
        assignment.status = AssignmentStatus.EXPIRED
        assignment.end_date = academic_year.end_date
        assignment.save(update_fields=["status", "end_date"])
        audit.log(
            action=AuditAction.ASSIGNMENT_EXPIRED,
            obj=assignment,
            summary=f"{assignment.faculty.full_name}, {assignment.committee.code}: expired at end of {academic_year.label}",
            detail={"end_date": academic_year.end_date.isoformat()},
        )
        count += 1
    return count


@transaction.atomic
def relinquish_assignment(*, assignment, order):
    """
    End an ACTIVE assignment with nobody taking over (BR-4).

    Invariants: the row is never deleted; status becomes RELINQUISHED,
    end_date the order's date and ending_order the issuing order;
    superseded_by stays null because nobody replaced them.
    """
    if assignment.status != AssignmentStatus.ACTIVE:
        raise AssignmentNotActive()
    if order.order_date < assignment.start_date:
        raise OrderDateInvalid(
            _("The order date is before the assignment began on %(date)s. Choose a later date.")
            % {"date": assignment.start_date.strftime("%d-%m-%Y")}
        )
    assignment.status = AssignmentStatus.RELINQUISHED
    assignment.end_date = order.order_date
    assignment.ending_order = order
    assignment.save(update_fields=["status", "end_date", "ending_order"])
    audit.log(
        action=AuditAction.ASSIGNMENT_RELINQUISHED,
        actor=order.issued_by,
        obj=assignment,
        summary=f"{assignment.faculty.full_name} relinquished {assignment.get_role_display()} of {assignment.committee.code} by {order.order_no}",
        detail={"order_no": order.order_no, "end_date": order.order_date.isoformat()},
    )
    return assignment


@transaction.atomic
def cancel_assignment(*, assignment, cancelling_order):
    """
    Void an assignment because the order that created it was cancelled (BR-6).

    Invariant: the row stays, marked CANCELLED, so the history still shows
    that the mistaken order existed and what it had done.
    """
    assignment.status = AssignmentStatus.CANCELLED
    assignment.end_date = cancelling_order.order_date
    assignment.ending_order = cancelling_order
    assignment.save(update_fields=["status", "end_date", "ending_order"])
    audit.log(
        action=AuditAction.ASSIGNMENT_CANCELLED,
        actor=cancelling_order.issued_by,
        obj=assignment,
        summary=f"{assignment.faculty.full_name}, {assignment.committee.code}: assignment cancelled by {cancelling_order.order_no}",
        detail={"order_no": cancelling_order.order_no},
    )
    return assignment


@transaction.atomic
def restore_superseded(*, assignment, actor=None):
    """
    Return a SUPERSEDED assignment to ACTIVE when the order that replaced it
    is cancelled (BR-6).

    Invariants: end_date, ending_order and superseded_by are cleared, because
    the event that ended it no longer stands. Refuses when the role is
    already filled again, rather than breaking uniq_active_convener.
    """
    if assignment.status != AssignmentStatus.SUPERSEDED:
        raise AssignmentNotActive(
            _("Only a superseded assignment can be restored.")
        )
    clash = (
        Assignment.objects.active()
        .filter(
            committee=assignment.committee,
            role=assignment.role,
            faculty=assignment.faculty,
        )
        .exists()
    )
    if assignment.role == AssignmentRole.CONVENER:
        clash = clash or current_convener(assignment.committee) is not None
    if clash:
        raise RestoreBlocked()

    assignment.status = AssignmentStatus.ACTIVE
    assignment.end_date = None
    assignment.ending_order = None
    assignment.superseded_by = None
    assignment.save(update_fields=["status", "end_date", "ending_order", "superseded_by"])
    audit.log(
        action=AuditAction.ASSIGNMENT_RESTORED,
        actor=actor,
        obj=assignment,
        summary=f"{assignment.faculty.full_name} restored as {assignment.get_role_display()} of {assignment.committee.code}",
        detail={"status": AssignmentStatus.ACTIVE},
    )
    return assignment
