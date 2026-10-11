"""
The assignment engine — the twelve groups in docs/05_TESTING.md §4.

This is the logic that protects order history. Each test asserts database
state, never just a return value.
"""

from datetime import date
from unittest.mock import patch

import pytest

from assignments.models import Assignment, AssignmentRole, AssignmentStatus
from assignments.services import (
    expire_assignments_for_year,
    relinquish_assignment,
    restore_superseded,
)
from audit.models import AuditLogEntry
from core.exceptions import (
    AssignmentConflict,
    AssignmentNotActive,
    CommitteeInactive,
    FacultyInactive,
    RestoreBlocked,
    RoleNotAllowed,
)
from orders.models import Order

pytestmark = pytest.mark.django_db


def test_1_convener_for_an_empty_committee_creates_one_active_row(
    faculty, committee, issue_order
):
    order = issue_order(faculty=faculty, committee=committee)
    assignment = Assignment.objects.get()
    assert assignment.status == AssignmentStatus.ACTIVE
    assert assignment.start_date == order.order_date
    assert assignment.issuing_order == order
    assert assignment.end_date is None


def test_2_new_convener_supersedes_the_previous_holder(
    faculty, other_faculty, committee, issue_order
):
    issue_order(faculty=faculty, committee=committee)
    new_order = issue_order(
        faculty=other_faculty, committee=committee, order_date=date(2026, 8, 1)
    )
    old = Assignment.objects.get(faculty=faculty)
    new = Assignment.objects.get(faculty=other_faculty)

    assert old.status == AssignmentStatus.SUPERSEDED
    assert old.end_date == new_order.order_date
    assert old.superseded_by == new
    assert old.ending_order == new_order
    assert Assignment.objects.count() == 2
    assert (
        Assignment.objects.active()
        .filter(committee=committee, role=AssignmentRole.CONVENER)
        .count()
        == 1
    )


def test_3_adding_a_member_leaves_existing_holders_untouched(
    faculty, other_faculty, third_faculty, committee, issue_order
):
    issue_order(faculty=faculty, committee=committee)
    issue_order(
        faculty=other_faculty,
        committee=committee,
        role=AssignmentRole.MEMBER,
        order_date=date(2026, 7, 2),
    )
    issue_order(
        faculty=third_faculty,
        committee=committee,
        role=AssignmentRole.MEMBER,
        order_date=date(2026, 7, 3),
    )
    assert Assignment.objects.active().count() == 3
    assert Assignment.objects.exclude(status=AssignmentStatus.ACTIVE).count() == 0


def test_4_duplicate_active_assignment_is_refused_and_writes_nothing(
    faculty, committee, issue_order
):
    issue_order(faculty=faculty, committee=committee)
    before = (Assignment.objects.count(), Order.objects.count())
    with pytest.raises(AssignmentConflict):
        issue_order(faculty=faculty, committee=committee, order_date=date(2026, 7, 8))
    assert (Assignment.objects.count(), Order.objects.count()) == before


def test_5_relinquish_ends_the_assignment_with_no_successor(
    faculty, committee, issue_order
):
    order = issue_order(faculty=faculty, committee=committee)
    ending = issue_order(
        faculty=faculty,
        committee=committee,
        role=AssignmentRole.MEMBER,
        order_date=date(2026, 7, 4),
    )
    assignment = order.created_assignments.get()
    relinquish_assignment(assignment=assignment, order=ending)
    assignment.refresh_from_db()

    assert assignment.status == AssignmentStatus.RELINQUISHED
    assert assignment.end_date == ending.order_date
    assert assignment.ending_order == ending
    assert assignment.superseded_by is None
    assert not Assignment.objects.active().filter(
        committee=committee, role=AssignmentRole.CONVENER
    )


def test_6_inactive_committee_is_refused(faculty, committee, issue_order):
    committee.is_active = False
    committee.save(update_fields=["is_active"])
    with pytest.raises(CommitteeInactive):
        issue_order(faculty=faculty, committee=committee)
    assert Assignment.objects.count() == 0


def test_7_inactive_faculty_is_refused(faculty, committee, issue_order):
    faculty.is_active = False
    faculty.save(update_fields=["is_active"])
    with pytest.raises(FacultyInactive):
        issue_order(faculty=faculty, committee=committee)
    assert Assignment.objects.count() == 0


def test_7b_member_on_a_convener_only_committee_is_refused(
    faculty, convener_only_committee, issue_order
):
    with pytest.raises(RoleNotAllowed):
        issue_order(
            faculty=faculty,
            committee=convener_only_committee,
            role=AssignmentRole.MEMBER,
        )
    assert Assignment.objects.count() == 0


def test_8_a_failure_midway_leaves_the_database_unchanged(
    faculty, other_faculty, committee, issue_order
):
    issue_order(faculty=faculty, committee=committee)
    before = (Assignment.objects.count(), Order.objects.count())

    with patch(
        "assignments.services.Assignment.objects.create",
        side_effect=RuntimeError("storage failed"),
    ):
        with pytest.raises(RuntimeError):
            issue_order(
                faculty=other_faculty, committee=committee, order_date=date(2026, 8, 2)
            )

    assert (Assignment.objects.count(), Order.objects.count()) == before
    assert Assignment.objects.get(faculty=faculty).status == AssignmentStatus.ACTIVE


def test_9_expiry_touches_only_that_years_active_rows(
    faculty, other_faculty, committee, exam_committee, issue_order, year, last_year
):
    old = issue_order(
        faculty=faculty,
        committee=committee,
        order_date=date(2025, 7, 1),
        academic_year=last_year,
    )
    current = issue_order(
        faculty=other_faculty, committee=exam_committee, order_date=date(2026, 7, 1)
    )

    expired = expire_assignments_for_year(last_year)

    old_assignment = old.created_assignments.get()
    current_assignment = current.created_assignments.get()
    old_assignment.refresh_from_db()
    current_assignment.refresh_from_db()

    assert expired == 1
    assert old_assignment.status == AssignmentStatus.EXPIRED
    assert old_assignment.end_date == last_year.end_date
    assert current_assignment.status == AssignmentStatus.ACTIVE


def test_9b_carried_forward_assignments_survive_the_rollover(
    faculty, committee, issue_order, last_year
):
    order = issue_order(
        faculty=faculty,
        committee=committee,
        order_date=date(2025, 7, 1),
        academic_year=last_year,
    )
    assignment = order.created_assignments.get()
    expire_assignments_for_year(last_year, carry_forward=[assignment])
    assignment.refresh_from_db()
    assert assignment.status == AssignmentStatus.ACTIVE


def test_10_restore_returns_a_superseded_row_to_active(
    faculty, other_faculty, committee, issue_order
):
    issue_order(faculty=faculty, committee=committee)
    issue_order(faculty=other_faculty, committee=committee, order_date=date(2026, 8, 3))
    superseded = Assignment.objects.get(faculty=faculty)
    replacement = Assignment.objects.get(faculty=other_faculty)

    # The replacement must stop being active first, as it would be after cancellation.
    Assignment.objects.filter(pk=replacement.pk).update(
        status=AssignmentStatus.CANCELLED, end_date=date(2026, 8, 3)
    )
    restore_superseded(assignment=superseded)
    superseded.refresh_from_db()

    assert superseded.status == AssignmentStatus.ACTIVE
    assert superseded.end_date is None
    assert superseded.superseded_by is None
    assert superseded.ending_order is None


def test_10b_restore_is_refused_when_the_role_is_filled_again(
    faculty, other_faculty, committee, issue_order
):
    issue_order(faculty=faculty, committee=committee)
    issue_order(faculty=other_faculty, committee=committee, order_date=date(2026, 8, 4))
    superseded = Assignment.objects.get(faculty=faculty)
    with pytest.raises(RestoreBlocked):
        restore_superseded(assignment=superseded)
    superseded.refresh_from_db()
    assert superseded.status == AssignmentStatus.SUPERSEDED


def test_10c_only_a_superseded_assignment_can_be_restored(
    faculty, committee, issue_order
):
    order = issue_order(faculty=faculty, committee=committee)
    with pytest.raises(AssignmentNotActive):
        restore_superseded(assignment=order.created_assignments.get())


def test_11_three_way_handover_produces_a_correct_chain(
    faculty, other_faculty, third_faculty, committee, issue_order
):
    issue_order(faculty=faculty, committee=committee, order_date=date(2026, 7, 1))
    issue_order(faculty=other_faculty, committee=committee, order_date=date(2026, 8, 1))
    issue_order(faculty=third_faculty, committee=committee, order_date=date(2026, 9, 1))

    first = Assignment.objects.get(faculty=faculty)
    second = Assignment.objects.get(faculty=other_faculty)
    third = Assignment.objects.get(faculty=third_faculty)

    assert first.superseded_by == second
    assert second.superseded_by == third
    assert third.superseded_by is None
    assert third.status == AssignmentStatus.ACTIVE
    assert [a.faculty for a in Assignment.objects.filter(committee=committee).order_by("start_date")] == [
        faculty,
        other_faculty,
        third_faculty,
    ]
    assert Assignment.objects.active().filter(committee=committee).count() == 1


def test_12_history_only_ever_grows(
    faculty, other_faculty, third_faculty, committee, exam_committee, issue_order
):
    operations = [
        (faculty, committee, AssignmentRole.CONVENER, date(2026, 7, 1)),
        (other_faculty, committee, AssignmentRole.MEMBER, date(2026, 7, 2)),
        (third_faculty, committee, AssignmentRole.MEMBER, date(2026, 7, 3)),
        (other_faculty, committee, AssignmentRole.CONVENER, date(2026, 7, 4)),
        (faculty, exam_committee, AssignmentRole.CONVENER, date(2026, 7, 5)),
        (third_faculty, exam_committee, AssignmentRole.MEMBER, date(2026, 7, 6)),
        (third_faculty, committee, AssignmentRole.CONVENER, date(2026, 7, 7)),
    ]
    for person, group, role, when in operations:
        issue_order(faculty=person, committee=group, role=role, order_date=when)

    assert Assignment.objects.count() == len(operations)
    # No row was ever removed: the highest id equals the number of rows.
    assert Assignment.objects.order_by("-pk").first().pk == len(operations)


def test_every_transition_is_recorded_in_the_audit_log(
    faculty, other_faculty, committee, issue_order
):
    issue_order(faculty=faculty, committee=committee)
    issue_order(faculty=other_faculty, committee=committee, order_date=date(2026, 8, 5))
    actions = set(AuditLogEntry.objects.values_list("action", flat=True))
    assert {"ORDER_ISSUED", "ASSIGNMENT_CREATED", "ASSIGNMENT_SUPERSEDED"} <= actions
