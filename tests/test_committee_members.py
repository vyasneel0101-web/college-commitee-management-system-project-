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


def test_the_edit_page_lists_members_with_tick_boxes(
    principal_client, faculty, committee, issue_order
):
    assignment = issue_order(faculty=faculty, committee=committee, role=AssignmentRole.MEMBER).created_assignments.get()
    html = principal_client.get(edit_url(committee)).content.decode()
    assert faculty.full_name in html
    assert f'name="id" value="{assignment.pk}"' in html
    assert reverse("orders:remove_members", kwargs={"committee_pk": committee.pk}) in html


def test_the_edit_page_offers_several_rows_to_add(principal_client, committee):
    html = principal_client.get(edit_url(committee)).content.decode()
    assert 'name="form-2-person"' in html, "three rows to start"
    assert "Add another person" in html


def remove_url(committee):
    return reverse("orders:remove_members", kwargs={"committee_pk": committee.pk})


def test_several_members_are_removed_in_one_order(
    principal_client, faculty, other_faculty, third_faculty, committee, issue_order
):
    order = issue_order(
        committee=committee,
        appointments=[
            (faculty, AssignmentRole.PRESIDING_OFFICER),
            (other_faculty, AssignmentRole.MEMBER),
            (third_faculty, AssignmentRole.MEMBER),
        ],
    )
    leaving = [a for a in order.created_assignments.all() if a.faculty != faculty]
    ids = [str(a.pk) for a in leaving]

    page = principal_client.get(remove_url(committee), {"id": ids}).content.decode()
    assert other_faculty.full_name in page and third_faculty.full_name in page
    assert faculty.full_name not in page.split("<main", 1)[1].split("</main>", 1)[0]

    before = Order.objects.count()
    response = principal_client.post(
        remove_url(committee),
        {"id": ids, "order_date": timezone.localdate().isoformat(), "remarks": ""},
    )
    assert response["Location"] == edit_url(committee)
    assert Order.objects.count() == before + 1, "one order for the whole removal"
    removal = Order.objects.filter(order_type=OrderType.RELINQUISHMENT).get()
    assert set(removal.ended_assignments.values_list("faculty", flat=True)) == {other_faculty.pk, third_faculty.pk}
    for a in leaving:
        a.refresh_from_db()
        assert a.status == AssignmentStatus.RELINQUISHED
    assert Assignment.objects.active().filter(committee=committee).get().faculty == faculty
    follow = principal_client.get(edit_url(committee)).content.decode()
    assert "2 people removed from" in follow


def test_the_removal_document_lists_everyone(
    principal, faculty, other_faculty, committee, issue_order
):
    order = issue_order(
        committee=committee,
        appointments=[(faculty, AssignmentRole.MEMBER), (other_faculty, AssignmentRole.MEMBER)],
    )
    removal = issue_relinquishment_order(
        assignments=list(order.created_assignments.all()),
        order_date=date(2026, 8, 1),
        issued_by=principal,
    )
    from docx import Document

    with removal.generated_file.open("rb") as handle:
        text = "\n".join(p.text for p in Document(handle).paragraphs)
    assert "relieved of their duties" in text
    assert faculty.full_name in text and other_faculty.full_name in text


def test_everyone_is_notified_once_about_a_bulk_removal(
    principal, faculty, other_faculty, third_faculty, committee, issue_order
):
    from notifications.models import Notification

    order = issue_order(
        committee=committee,
        appointments=[
            (faculty, AssignmentRole.PRESIDING_OFFICER),
            (other_faculty, AssignmentRole.MEMBER),
            (third_faculty, AssignmentRole.MEMBER),
        ],
    )
    leaving = [a for a in order.created_assignments.all() if a.faculty != faculty]
    before = Notification.objects.count()
    issue_relinquishment_order(assignments=leaving, order_date=date(2026, 8, 1), issued_by=principal)
    assert Notification.objects.count() == before + 3, "the two removed and the one staying, once each"


def test_nothing_ticked_goes_back_with_a_message(principal_client, committee):
    response = principal_client.get(remove_url(committee))
    assert response["Location"] == edit_url(committee)
    assert "Tick at least one person" in principal_client.get(edit_url(committee)).content.decode()


def test_someone_from_another_committee_cannot_be_slipped_in(
    principal_client, faculty, other_faculty, committee, exam_committee, issue_order
):
    issue_order(faculty=faculty, committee=committee, role=AssignmentRole.MEMBER)
    elsewhere = issue_order(faculty=other_faculty, committee=exam_committee, role=AssignmentRole.MEMBER).created_assignments.get()
    principal_client.post(
        remove_url(committee),
        {"id": [str(elsewhere.pk)], "order_date": timezone.localdate().isoformat(), "remarks": ""},
    )
    elsewhere.refresh_from_db()
    assert elsewhere.status == AssignmentStatus.ACTIVE


def test_adding_several_members_from_the_edit_page_is_one_order(
    principal_client, faculty, other_faculty, committee, year
):
    payload = {
        "committee": committee.pk,
        "order_date": timezone.localdate().isoformat(),
        "references": "",
        "remarks": "",
        "step": "issue",
        "expected_superseded": "none",
        "form-TOTAL_FORMS": "3",
        "form-INITIAL_FORMS": "0",
        "form-MIN_NUM_FORMS": "0",
        "form-MAX_NUM_FORMS": "20",
        "form-0-person": f"u:{faculty.pk}",
        "form-0-role": AssignmentRole.PRESIDING_OFFICER,
        "form-1-person": f"u:{other_faculty.pk}",
        "form-1-role": AssignmentRole.MEMBER,
        "form-2-person": "",
        "form-2-role": "",
    }
    principal_client.post(reverse("orders:assign"), payload)
    assert Order.objects.count() == 1
    assert Order.objects.get().created_assignments.count() == 2


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
