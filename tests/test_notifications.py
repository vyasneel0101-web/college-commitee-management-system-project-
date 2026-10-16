"""Committee members are told about every change to their committee."""

from datetime import date
from unittest.mock import patch

import pytest
from django.urls import reverse

from assignments.models import AssignmentRole
from notifications.models import Notification
from orders.services import cancel_order, issue_relinquishment_order

pytestmark = pytest.mark.django_db
MEMBER, LEAD = AssignmentRole.MEMBER, AssignmentRole.PRESIDING_OFFICER


def inbox(person):
    return list(Notification.objects.filter(recipient=person).values_list("message", flat=True))


def test_the_person_appointed_is_notified(faculty, committee, issue_order):
    issue_order(faculty=faculty, committee=committee, role=MEMBER)
    messages = inbox(faculty)
    assert len(messages) == 1
    assert f"{faculty.full_name} appointed Member" in messages[0]
    assert committee.name in messages[0]


def test_existing_members_are_told_when_someone_joins(
    faculty, other_faculty, committee, issue_order
):
    issue_order(faculty=faculty, committee=committee, role=MEMBER)
    issue_order(faculty=other_faculty, committee=committee, role=MEMBER, order_date=date(2026, 7, 2))
    joined = f"{other_faculty.full_name} appointed Member"
    assert any(joined in m for m in inbox(faculty)), "the existing member"
    assert any(joined in m for m in inbox(other_faculty)), "the newcomer"


def test_everyone_is_told_when_a_member_is_removed(
    principal, faculty, other_faculty, committee, issue_order
):
    issue_order(faculty=faculty, committee=committee, role=MEMBER)
    leaving = issue_order(
        faculty=other_faculty, committee=committee, role=MEMBER, order_date=date(2026, 7, 2)
    ).created_assignments.get()
    issue_relinquishment_order(assignment=leaving, order_date=date(2026, 8, 1), issued_by=principal)
    removed = f"{other_faculty.full_name} removed as Member"
    assert any(removed in m for m in inbox(faculty)), "the remaining member"
    assert any(removed in m for m in inbox(other_faculty)), "the person removed"


def test_the_person_superseded_is_told(faculty, other_faculty, committee, issue_order):
    issue_order(faculty=faculty, committee=committee, role=LEAD)
    issue_order(faculty=other_faculty, committee=committee, role=LEAD, order_date=date(2026, 8, 1))
    assert any(f"{faculty.full_name} is no longer Presiding Officer" in m for m in inbox(faculty))


def test_a_cancellation_reaches_the_withdrawn_and_the_restored(
    principal, faculty, other_faculty, committee, issue_order
):
    issue_order(faculty=faculty, committee=committee, role=LEAD)
    mistake = issue_order(
        faculty=other_faculty, committee=committee, role=LEAD, order_date=date(2026, 8, 1)
    )
    cancel_order(order=mistake, reason="Wrong person named.", issued_by=principal)
    assert any(
        "cancelled" in m and f"{faculty.full_name} is Presiding Officer again" in m
        for m in inbox(faculty)
    )
    assert any(
        f"{other_faculty.full_name} is no longer Presiding Officer" in m
        for m in inbox(other_faculty)
    )


def test_other_committees_are_not_disturbed(
    faculty, other_faculty, committee, exam_committee, issue_order
):
    issue_order(faculty=faculty, committee=committee, role=MEMBER)
    issue_order(faculty=other_faculty, committee=exam_committee, role=MEMBER)
    assert all(exam_committee.name not in m for m in inbox(faculty))


def test_the_principal_is_not_notified_of_their_own_action(
    principal, faculty, committee, issue_order
):
    issue_order(faculty=faculty, committee=committee, role=MEMBER)
    assert inbox(principal) == []


def test_an_external_member_does_not_break_notifying(
    faculty, external_member, committee, issue_order
):
    issue_order(
        committee=committee,
        appointments=[(faculty, LEAD), (external_member, AssignmentRole.EXTERNAL_MEMBER)],
    )
    assert len(inbox(faculty)) == 1


def test_a_failed_order_leaves_no_notification(faculty, committee, issue_order):
    with patch("assignments.services.Assignment.objects.create", side_effect=RuntimeError):
        with pytest.raises(RuntimeError):
            issue_order(faculty=faculty, committee=committee, role=MEMBER)
    assert Notification.objects.count() == 0


def test_the_header_shows_the_unread_count(faculty_client, faculty, committee, issue_order):
    issue_order(faculty=faculty, committee=committee, role=MEMBER)
    html = faculty_client.get(reverse("assignments:dashboard")).content.decode()
    assert 'aria-label="1 unread"' in html


def test_the_dashboard_lists_recent_updates(faculty_client, faculty, committee, issue_order):
    issue_order(faculty=faculty, committee=committee, role=MEMBER)
    html = faculty_client.get(reverse("assignments:dashboard")).content.decode()
    assert "Recent updates" in html
    assert f"{faculty.full_name} appointed Member" in html


def test_opening_the_list_marks_everything_read(faculty_client, faculty, committee, issue_order):
    issue_order(faculty=faculty, committee=committee, role=MEMBER)
    first = faculty_client.get(reverse("notifications:list")).content.decode()
    assert ">New<" in first, "still highlighted on the visit that reads them"
    assert Notification.objects.unread().count() == 0
    html = faculty_client.get(reverse("assignments:dashboard")).content.decode()
    assert "unread" not in html


def test_you_only_see_your_own(
    client, faculty, other_faculty, committee, exam_committee, issue_order
):
    issue_order(faculty=faculty, committee=committee, role=MEMBER)
    issue_order(faculty=other_faculty, committee=exam_committee, role=MEMBER)
    client.force_login(faculty)
    html = client.get(reverse("notifications:list")).content.decode()
    assert other_faculty.full_name not in html


def test_the_list_links_to_the_committee_a_member_can_open(
    faculty_client, faculty, other_faculty, committee, issue_order
):
    """A member told about someone else joining cannot open that order; the committee page they can."""
    issue_order(faculty=faculty, committee=committee, role=MEMBER)
    issue_order(faculty=other_faculty, committee=committee, role=MEMBER, order_date=date(2026, 7, 2))
    html = faculty_client.get(reverse("notifications:list")).content.decode()
    link = reverse("committees:detail", kwargs={"pk": committee.pk})
    assert link in html
    assert faculty_client.get(link).status_code == 200
