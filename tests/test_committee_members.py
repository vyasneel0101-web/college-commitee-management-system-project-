"""Managing a committee's members from its edit page."""

from datetime import date

import pytest
from django.urls import reverse
from django.utils import timezone

from assignments.models import Assignment, AssignmentRole, AssignmentStatus
from orders.models import Order, OrderType
from orders.services import cancel_order, issue_relinquishment_order

pytestmark = pytest.mark.django_db


def edit_url(committee):
    return reverse("committees:edit", kwargs={"pk": committee.pk})


def test_the_edit_page_lists_members_with_a_remove_link(
    principal_client, faculty, committee, issue_order
):
    assignment = issue_order(faculty=faculty, committee=committee, role=AssignmentRole.MEMBER).created_assignments.get()
    html = principal_client.get(edit_url(committee)).content.decode()
    assert faculty.full_name in html
    assert reverse("orders:relinquish", kwargs={"pk": assignment.pk}) in html


def test_an_empty_committee_says_so(principal_client, committee):
    assert "Nobody is on this committee yet." in principal_client.get(edit_url(committee)).content.decode()


def test_adding_a_member_from_the_edit_page_goes_to_the_preview(
    principal_client, faculty, committee, year
):
    payload = {
        "committee": committee.pk,
        "order_date": timezone.localdate().isoformat(),
        "references": "",
        "remarks": "",
        "step": "preview",
        "form-TOTAL_FORMS": "1",
        "form-INITIAL_FORMS": "0",
        "form-MIN_NUM_FORMS": "0",
        "form-MAX_NUM_FORMS": "20",
        "form-0-person": f"u:{faculty.pk}",
        "form-0-role": AssignmentRole.MEMBER,
    }
    preview = principal_client.post(reverse("orders:assign"), payload).content.decode()
    assert "Issue order" in preview and faculty.full_name in preview
    assert Order.objects.count() == 0, "the preview saves nothing"

    response = principal_client.post(
        reverse("orders:assign"), dict(payload, step="issue", expected_superseded="none")
    )
    assert response.status_code == 302
    assert Assignment.objects.active().get().faculty == faculty


def test_removing_a_member_issues_an_order_and_returns_to_the_edit_page(
    principal_client, faculty, committee, issue_order
):
    assignment = issue_order(faculty=faculty, committee=committee, role=AssignmentRole.MEMBER).created_assignments.get()
    url = reverse("orders:relinquish", kwargs={"pk": assignment.pk})
    page = principal_client.get(url, {"next": edit_url(committee)}).content.decode()
    assert "Remove from committee" in page

    response = principal_client.post(
        url, {"order_date": timezone.localdate().isoformat(), "remarks": "", "next": edit_url(committee)}
    )
    assignment.refresh_from_db()
    assert response.status_code == 302 and response["Location"] == edit_url(committee)
    assert assignment.status == AssignmentStatus.RELINQUISHED, "ended, never erased"
    assert Order.objects.filter(order_type=OrderType.RELINQUISHMENT).count() == 1
    follow = principal_client.get(edit_url(committee)).content.decode()
    assert f"{faculty.full_name} removed from" in follow


def test_an_off_site_return_address_is_ignored(principal_client, faculty, committee, issue_order):
    assignment = issue_order(faculty=faculty, committee=committee, role=AssignmentRole.MEMBER).created_assignments.get()
    response = principal_client.post(
        reverse("orders:relinquish", kwargs={"pk": assignment.pk}),
        {"order_date": timezone.localdate().isoformat(), "remarks": "", "next": "https://evil.example.com/"},
    )
    assert response["Location"].startswith("/orders/")


def test_faculty_cannot_see_the_member_controls(faculty_client, committee):
    assert faculty_client.get(edit_url(committee)).status_code == 403


def test_the_preview_no_longer_offers_tick_boxes(
    principal_client, faculty, other_faculty, committee, issue_order, year
):
    issue_order(faculty=faculty, committee=committee, role=AssignmentRole.MEMBER)
    from test_views import assign_payload

    html = principal_client.post(
        reverse("orders:assign"), assign_payload(committee, [(other_faculty, AssignmentRole.MEMBER)])
    ).content.decode()
    assert 'name="relieve"' not in html


def test_cancelling_a_removal_puts_the_member_back(principal, faculty, committee, issue_order):
    assignment = issue_order(faculty=faculty, committee=committee).created_assignments.get()
    removal = issue_relinquishment_order(
        assignment=assignment, order_date=date(2026, 8, 1), issued_by=principal
    )
    cancel_order(order=removal, reason="Removed by mistake.", issued_by=principal)
    assignment.refresh_from_db()
    assert assignment.status == AssignmentStatus.ACTIVE
