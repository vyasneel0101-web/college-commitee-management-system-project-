"""Edge cases for notifications, written to find failures rather than confirm successes."""

from datetime import date
from unittest.mock import patch

import pytest
from django.urls import reverse

from assignments.models import AssignmentRole
from core.exceptions import RestoreBlocked
from notifications.models import Notification
from orders.services import cancel_order, issue_relinquishment_order

pytestmark = pytest.mark.django_db
MEMBER, LEAD, NODAL = AssignmentRole.MEMBER, AssignmentRole.PRESIDING_OFFICER, AssignmentRole.NODAL_OFFICER


def count(person):
    return Notification.objects.filter(recipient=person).count()


def messages(person):
    return list(Notification.objects.filter(recipient=person).values_list("message", flat=True))


def test_several_people_on_one_order_each_get_exactly_one(
    faculty, other_faculty, third_faculty, committee, issue_order
):
    issue_order(
        committee=committee,
        appointments=[(faculty, LEAD), (other_faculty, MEMBER), (third_faculty, MEMBER)],
    )
    assert (count(faculty), count(other_faculty), count(third_faculty)) == (1, 1, 1)


def test_someone_with_two_roles_on_a_committee_is_told_once(
    faculty, other_faculty, committee, issue_order
):
    issue_order(faculty=faculty, committee=committee, role=MEMBER)
    issue_order(faculty=faculty, committee=committee, role=NODAL, order_date=date(2026, 7, 2))
    before = count(faculty)
    issue_order(faculty=other_faculty, committee=committee, role=MEMBER, order_date=date(2026, 7, 3))
    assert count(faculty) == before + 1


def test_after_removal_you_hear_nothing_more_about_that_committee(
    principal, faculty, other_faculty, third_faculty, committee, issue_order
):
    mine = issue_order(faculty=faculty, committee=committee, role=MEMBER).created_assignments.get()
    issue_order(faculty=other_faculty, committee=committee, role=MEMBER, order_date=date(2026, 7, 2))
    issue_relinquishment_order(assignment=mine, order_date=date(2026, 7, 3), issued_by=principal)
    before = count(faculty)
    issue_order(faculty=third_faculty, committee=committee, role=MEMBER, order_date=date(2026, 7, 4))
    assert count(faculty) == before


def test_a_superseded_lead_hears_nothing_more_afterwards(
    faculty, other_faculty, third_faculty, committee, issue_order
):
    issue_order(faculty=faculty, committee=committee, role=LEAD)
    issue_order(faculty=other_faculty, committee=committee, role=LEAD, order_date=date(2026, 7, 2))
    before = count(faculty)
    issue_order(faculty=third_faculty, committee=committee, role=MEMBER, order_date=date(2026, 7, 3))
    assert count(faculty) == before


def test_cancelling_a_removal_tells_the_member_they_are_back(
    principal, faculty, other_faculty, committee, issue_order
):
    issue_order(faculty=other_faculty, committee=committee, role=LEAD)
    mine = issue_order(faculty=faculty, committee=committee, role=MEMBER, order_date=date(2026, 7, 2)).created_assignments.get()
    removal = issue_relinquishment_order(assignment=mine, order_date=date(2026, 7, 3), issued_by=principal)
    cancel_order(order=removal, reason="Removed by mistake.", issued_by=principal)
    assert any(f"{faculty.full_name} is Member again" in m for m in messages(faculty))
    assert any(f"{faculty.full_name} is Member again" in m for m in messages(other_faculty))


def test_a_refused_cancellation_sends_nothing(
    principal, faculty, other_faculty, third_faculty, committee, issue_order
):
    issue_order(faculty=faculty, committee=committee, role=LEAD)
    second = issue_order(faculty=other_faculty, committee=committee, role=LEAD, order_date=date(2026, 7, 2))
    issue_order(faculty=third_faculty, committee=committee, role=LEAD, order_date=date(2026, 7, 3))
    before = Notification.objects.count()
    with pytest.raises(RestoreBlocked):
        # The first lead cannot be restored: a third order filled the role again.
        cancel_order(order=second, reason="Testing a refused cancellation.", issued_by=principal)
    assert Notification.objects.count() == before


def test_a_failed_order_after_numbering_sends_nothing(faculty, other_faculty, committee, issue_order):
    issue_order(faculty=faculty, committee=committee, role=MEMBER)
    before = Notification.objects.count()
    with patch("orders.services.notify_committee", side_effect=RuntimeError("boom")):
        with pytest.raises(RuntimeError):
            issue_order(faculty=other_faculty, committee=committee, role=MEMBER, order_date=date(2026, 7, 2))
    assert Notification.objects.count() == before
    assert count(other_faculty) == 0


def test_a_deactivated_member_is_still_on_record_but_cannot_read(
    client, faculty, other_faculty, committee, issue_order
):
    issue_order(faculty=faculty, committee=committee, role=MEMBER)
    faculty.is_active = False
    faculty.save(update_fields=["is_active"])
    issue_order(faculty=other_faculty, committee=committee, role=MEMBER, order_date=date(2026, 7, 2))
    client.force_login(faculty)
    assert client.get(reverse("notifications:list")).status_code == 302, "cannot sign in"


def test_nobody_sees_anyone_elses_notifications_by_guessing(
    faculty_client, other_faculty, committee, issue_order
):
    issue_order(faculty=other_faculty, committee=committee, role=MEMBER)
    html = faculty_client.get(reverse("notifications:list")).content.decode()
    assert other_faculty.full_name not in html


def test_reading_your_own_does_not_mark_anyone_elses_read(
    faculty_client, faculty, other_faculty, committee, issue_order
):
    issue_order(
        committee=committee, appointments=[(faculty, LEAD), (other_faculty, MEMBER)]
    )
    faculty_client.get(reverse("notifications:list"))
    assert Notification.objects.filter(recipient=other_faculty, read_at__isnull=True).count() == 1


def test_editing_a_committee_tells_its_members(
    principal_client, faculty, other_faculty, committee, issue_order
):
    """'Any changes performed to that committee' — including its own details."""
    issue_order(committee=committee, appointments=[(faculty, LEAD), (other_faculty, MEMBER)])
    before = (count(faculty), count(other_faculty))
    principal_client.post(
        reverse("committees:edit", kwargs={"pk": committee.pk}),
        {
            "name": "Training and Placement Cell",
            "code": committee.code,
            "description": "Now also handles internships.",
            "allows_multiple_members": "on",
            "is_active": "on",
        },
    )
    assert (count(faculty), count(other_faculty)) == (before[0] + 1, before[1] + 1)
    assert any("Training and Placement Cell" in m for m in messages(faculty))


def test_saving_a_committee_unchanged_tells_nobody(
    principal_client, faculty, committee, issue_order
):
    issue_order(faculty=faculty, committee=committee, role=MEMBER)
    before = count(faculty)
    principal_client.post(
        reverse("committees:edit", kwargs={"pk": committee.pk}),
        {
            "name": committee.name,
            "code": committee.code,
            "description": committee.description,
            "allows_multiple_members": "on",
            "is_active": "on",
        },
    )
    assert count(faculty) == before
