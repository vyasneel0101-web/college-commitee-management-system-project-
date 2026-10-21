"""The register must describe every order type without losing official history."""

from datetime import date
import re

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils.html import escape

from assignments.models import AssignmentRole
from orders.services import cancel_order, issue_relinquishment_order

pytestmark = pytest.mark.django_db


def register_row(client, order):
    html = client.get(reverse("orders:register")).content.decode()
    link = reverse("orders:detail", kwargs={"pk": order.pk})
    return next(row for row in re.findall(r"<tr\b.*?</tr>", html, re.S) if f'href="{link}"' in row)


def test_removal_order_names_the_person_and_effect(principal_client, principal, faculty, committee, issue_order):
    assignment = issue_order(faculty=faculty, committee=committee).created_assignments.get()
    removal = issue_relinquishment_order(
        assignment=assignment, order_date=date(2026, 8, 1), issued_by=principal
    )
    before = removal.generated_file.read()
    row = register_row(principal_client, removal)
    assert escape(faculty.full_name) in row
    assert "Presiding Officer" in row
    assert "Relinquished" in row
    assert reverse("orders:download", kwargs={"pk": removal.pk}) in row
    removal.refresh_from_db()
    with removal.generated_file.open("rb") as handle:
        assert handle.read() == before


def test_bulk_removal_lists_staff_and_external_members(
    principal_client, principal, faculty, external_member, committee, issue_order
):
    order = issue_order(
        committee=committee,
        appointments=[(faculty, AssignmentRole.MEMBER), (external_member, AssignmentRole.EXTERNAL_MEMBER)],
    )
    removal = issue_relinquishment_order(
        assignments=list(order.created_assignments.all()),
        order_date=date(2026, 8, 1), issued_by=principal,
    )
    row = register_row(principal_client, removal)
    assert escape(faculty.full_name) in row
    assert escape(external_member.full_name) in row
    assert "External Member" in row
    assert "Relinquished" in row


def test_correction_lists_both_withdrawn_and_restored_people(
    principal_client, principal, faculty, other_faculty, committee, issue_order
):
    issue_order(faculty=faculty, committee=committee)
    replacement = issue_order(
        faculty=other_faculty, committee=committee, order_date=date(2026, 8, 1)
    )
    correction = cancel_order(order=replacement, reason="Wrong person.", issued_by=principal)
    row = register_row(principal_client, correction)
    assert escape(faculty.full_name) in row and "Restored" in row
    assert escape(other_faculty.full_name) in row and "Withdrawn" in row
    assert "Correction issued" in row
    assert "Cancelled" in register_row(principal_client, replacement)


def test_cancelled_removal_keeps_names_after_the_assignment_is_restored(
    principal_client, principal, faculty, committee, issue_order
):
    assignment = issue_order(faculty=faculty, committee=committee).created_assignments.get()
    removal = issue_relinquishment_order(
        assignment=assignment, order_date=date(2026, 8, 1), issued_by=principal
    )
    correction = cancel_order(order=removal, reason="Removed by mistake.", issued_by=principal)
    assert not removal.ended_assignments.exists()
    row = register_row(principal_client, removal)
    assert escape(faculty.full_name) in row
    assert "Removal cancelled" in row
    correction_row = register_row(principal_client, correction)
    assert escape(faculty.full_name) in correction_row and "Restored" in correction_row


def test_register_query_count_does_not_grow_for_external_appointments(
    principal_client, faculty, external_member, committee, exam_committee, issue_order
):
    issue_order(committee=committee, appointments=[(external_member, AssignmentRole.EXTERNAL_MEMBER)])
    with CaptureQueriesContext(connection) as small:
        response = principal_client.get(reverse("orders:register"))
        assert escape(external_member.full_name) in response.content.decode()
    issue_order(
        committee=exam_committee,
        appointments=[(external_member, AssignmentRole.EXTERNAL_MEMBER), (faculty, AssignmentRole.MEMBER)],
    )
    with CaptureQueriesContext(connection) as larger:
        html = principal_client.get(reverse("orders:register")).content.decode()
        assert escape(faculty.full_name) in html
    assert len(larger) == len(small)
