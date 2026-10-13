"""
Ending people's current roles in the same order that appoints others: moving
someone between committees, or replacing one member with another.
"""

from datetime import date

import pytest
from django.urls import reverse
from docx import Document

from assignments.models import Assignment, AssignmentRole, AssignmentStatus
from core.exceptions import DuplicateAppointment, PreviewOutdated
from orders.models import Order
from orders.services import cancel_order, relieve_candidates

from test_views import assign_payload

pytestmark = pytest.mark.django_db
MEMBER = AssignmentRole.MEMBER
LEAD = AssignmentRole.PRESIDING_OFFICER


def text_of(order):
    with order.generated_file.open("rb") as handle:
        return "\n".join(p.text for p in Document(handle).paragraphs)


def test_moving_someone_to_another_committee_ends_their_old_role(
    faculty, committee, exam_committee, issue_order
):
    """Mihir leaves TPU and joins EXAM: one order does both."""
    old = issue_order(faculty=faculty, committee=committee, role=MEMBER).created_assignments.get()
    order = issue_order(
        committee=exam_committee,
        faculty=faculty,
        role=MEMBER,
        order_date=date(2026, 8, 1),
        relieve=[old],
    )
    old.refresh_from_db()
    assert old.status == AssignmentStatus.RELINQUISHED
    assert old.end_date == date(2026, 8, 1)
    assert old.ending_order == order
    assert Assignment.objects.active().get(faculty=faculty).committee == exam_committee


def test_replacing_one_member_with_another(
    faculty, other_faculty, committee, issue_order
):
    old = issue_order(faculty=faculty, committee=committee, role=MEMBER).created_assignments.get()
    issue_order(
        committee=committee,
        faculty=other_faculty,
        role=MEMBER,
        order_date=date(2026, 8, 1),
        relieve=[old],
    )
    old.refresh_from_db()
    active = Assignment.objects.active().filter(committee=committee)
    assert old.status == AssignmentStatus.RELINQUISHED
    assert [a.faculty for a in active] == [other_faculty]


def test_cancelling_a_swap_puts_the_old_member_back(
    principal, faculty, other_faculty, committee, issue_order
):
    old = issue_order(faculty=faculty, committee=committee, role=MEMBER).created_assignments.get()
    swap = issue_order(
        committee=committee,
        faculty=other_faculty,
        role=MEMBER,
        order_date=date(2026, 8, 1),
        relieve=[old],
    )
    cancel_order(order=swap, reason="Wrong member replaced.", issued_by=principal)
    old.refresh_from_db()
    newcomer = Assignment.objects.get(faculty=other_faculty)
    assert old.status == AssignmentStatus.ACTIVE
    assert old.end_date is None and old.ending_order is None
    assert newcomer.status == AssignmentStatus.CANCELLED


def test_cancelling_a_relinquishment_order_restores_the_role(
    principal, faculty, committee, issue_order
):
    from orders.services import issue_relinquishment_order

    assignment = issue_order(faculty=faculty, committee=committee).created_assignments.get()
    ending = issue_relinquishment_order(
        assignment=assignment, order_date=date(2026, 8, 1), issued_by=principal
    )
    cancel_order(order=ending, reason="Relieved by mistake.", issued_by=principal)
    assignment.refresh_from_db()
    assert assignment.status == AssignmentStatus.ACTIVE


def test_nothing_is_relieved_unless_ticked(faculty, committee, exam_committee, issue_order):
    issue_order(faculty=faculty, committee=committee, role=MEMBER)
    issue_order(committee=exam_committee, faculty=faculty, role=MEMBER, order_date=date(2026, 8, 1))
    assert Assignment.objects.active().filter(faculty=faculty).count() == 2


def test_the_current_lead_cannot_also_be_ticked_when_a_new_lead_is_named(
    faculty, other_faculty, committee, issue_order
):
    lead = issue_order(faculty=faculty, committee=committee).created_assignments.get()
    with pytest.raises(DuplicateAppointment):
        issue_order(
            committee=committee,
            faculty=other_faculty,
            order_date=date(2026, 8, 1),
            relieve=[lead],
        )
    assert Order.objects.count() == 1


def test_a_role_that_already_ended_cannot_be_relieved(
    principal, faculty, other_faculty, committee, issue_order
):
    old = issue_order(faculty=faculty, committee=committee, role=MEMBER).created_assignments.get()
    Assignment.objects.filter(pk=old.pk).update(
        status=AssignmentStatus.RELINQUISHED, end_date=date(2026, 7, 20)
    )
    old.refresh_from_db()
    with pytest.raises(PreviewOutdated):
        issue_order(
            committee=committee,
            faculty=other_faculty,
            role=MEMBER,
            order_date=date(2026, 8, 1),
            relieve=[old],
        )


def test_candidates_are_the_appointees_roles_and_this_committees_members(
    faculty, other_faculty, third_faculty, committee, exam_committee, issue_order
):
    lead = issue_order(faculty=third_faculty, committee=committee).created_assignments.get()
    member = issue_order(faculty=other_faculty, committee=committee, role=MEMBER).created_assignments.get()
    elsewhere = issue_order(faculty=faculty, committee=exam_committee, role=MEMBER).created_assignments.get()

    candidates = relieve_candidates(committee=committee, appointments=[(faculty, MEMBER)])
    assert elsewhere in candidates, "the appointee's role on another committee"
    assert member in candidates, "an existing member of this committee"
    assert lead not in candidates, "the person in charge is superseded, not relieved"


def test_the_order_document_lists_who_is_relieved(
    faculty, other_faculty, table_committee, issue_order
):
    old = issue_order(
        faculty=faculty, committee=table_committee, role=MEMBER
    ).created_assignments.get()
    order = issue_order(
        committee=table_committee,
        faculty=other_faculty,
        role=MEMBER,
        order_date=date(2026, 8, 1),
        relieve=[old],
    )
    text = text_of(order)
    assert "stand relieved of their earlier duties" in text
    assert faculty.full_name in text


def test_the_preview_offers_tick_boxes_and_issue_honours_them(
    principal_client, faculty, other_faculty, committee, issue_order
):
    old = issue_order(faculty=faculty, committee=committee, role=MEMBER).created_assignments.get()
    payload = assign_payload(committee, [(other_faculty, MEMBER)])
    preview = principal_client.post(reverse("orders:assign"), payload).content.decode()
    assert f'name="relieve" value="{old.pk}"' in preview

    payload.update(step="issue", expected_superseded="none", relieve=[str(old.pk)])
    response = principal_client.post(reverse("orders:assign"), payload)
    old.refresh_from_db()
    assert response.status_code == 302
    assert old.status == AssignmentStatus.RELINQUISHED


def test_the_order_page_says_who_was_relieved(
    principal_client, faculty, other_faculty, committee, issue_order
):
    old = issue_order(faculty=faculty, committee=committee, role=MEMBER).created_assignments.get()
    order = issue_order(
        committee=committee,
        faculty=other_faculty,
        role=MEMBER,
        order_date=date(2026, 8, 1),
        relieve=[old],
    )
    html = principal_client.get(reverse("orders:detail", kwargs={"pk": order.pk})).content.decode()
    assert "Relieved <strong>" in html and faculty.full_name in html
