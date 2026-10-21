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


def cell_blocks(row, label):
    cell = re.search(r'<td data-label="' + re.escape(label) + r'"[^>]*>.*?</td>', row, re.S).group(0)
    return re.findall(r'<div class="register-recipient">.*?</div>', cell, re.S)


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


def test_each_recipient_has_official_details_and_their_own_status_tag(
    principal_client, principal, faculty, other_faculty, committee, issue_order
):
    order = issue_order(
        committee=committee,
        appointments=[(faculty, AssignmentRole.PRESIDING_OFFICER), (other_faculty, AssignmentRole.MEMBER)],
    )
    issue_relinquishment_order(
        assignment=order.created_assignments.get(faculty=other_faculty),
        order_date=date(2026, 8, 1), issued_by=principal,
    )
    row = register_row(principal_client, order)
    recipients = cell_blocks(row, "Issued to")
    effects = cell_blocks(row, "Assignment / order effect")
    assert len(recipients) == len(effects) == 2
    for person, role, status, tag in (
        (faculty, "Presiding Officer", "Active", "pill-active"),
        (other_faculty, "Member", "Relinquished", "pill-history"),
    ):
        recipient = next(block for block in recipients if escape(person.full_name) in block)
        assert person.salutation in recipient
        assert role in recipient and "pill-role" in recipient
        assert escape(person.get_designation_display()) in recipient
        assert escape(person.department.name) in recipient
        effect = next(block for block in effects if escape(person.full_name) in block)
        assert role in effect and status in effect and tag in effect


def test_external_recipient_shows_organisation_and_role(
    principal_client, external_member, committee, issue_order
):
    order = issue_order(committee=committee, appointments=[(external_member, AssignmentRole.EXTERNAL_MEMBER)])
    recipient = cell_blocks(register_row(principal_client, order), "Issued to")[0]
    assert external_member.salutation in recipient
    assert escape(external_member.organisation) in recipient
    assert "External Member" in recipient


def test_register_preserves_saved_names_and_department_after_profile_changes(
    principal_client, faculty, committee, issue_order
):
    order = issue_order(faculty=faculty, committee=committee)
    original_name, original_department = faculty.full_name, faculty.department.name
    faculty.full_name = "Test Corrected Name"
    faculty.department = None
    faculty.save(update_fields=["full_name", "department"])
    row = register_row(principal_client, order)
    assert escape(original_name) in row and escape(original_department) in row
    assert faculty.full_name not in row


def test_cancelled_removal_correction_keeps_saved_person_details(
    principal_client, principal, faculty, committee, issue_order
):
    assignment = issue_order(faculty=faculty, committee=committee).created_assignments.get()
    removal = issue_relinquishment_order(
        assignment=assignment, order_date=date(2026, 8, 1), issued_by=principal
    )
    correction = cancel_order(order=removal, reason="Removed by mistake.", issued_by=principal)
    row = register_row(principal_client, correction)
    recipient = cell_blocks(row, "Issued to")[0]
    assert escape(faculty.department.name) in recipient
    assert "Presiding Officer" in recipient
    effect = cell_blocks(row, "Assignment / order effect")[0]
    assert "Restored" in effect and "pill-active" in effect


def test_two_roles_for_the_same_person_keep_separate_status_tags(
    principal_client, principal, faculty, committee, issue_order
):
    order = issue_order(
        committee=committee,
        appointments=[(faculty, AssignmentRole.PRESIDING_OFFICER), (faculty, AssignmentRole.MEMBER)],
    )
    issue_relinquishment_order(
        assignment=order.created_assignments.get(role=AssignmentRole.MEMBER),
        order_date=date(2026, 8, 1), issued_by=principal,
    )
    effects = cell_blocks(register_row(principal_client, order), "Assignment / order effect")
    assert len(effects) == 2
    lead = next(block for block in effects if "Presiding Officer" in block)
    member = next(block for block in effects if "Presiding Officer" not in block)
    assert "Active" in lead and "pill-active" in lead
    assert "Relinquished" in member and "pill-history" in member


def test_correction_recipient_details_do_not_add_queries_per_order(
    principal_client, principal, faculty, other_faculty, committee, exam_committee, issue_order
):
    first = issue_order(faculty=faculty, committee=committee)
    cancel_order(order=first, reason="Test correction.", issued_by=principal)
    with CaptureQueriesContext(connection) as small:
        assert escape(faculty.full_name) in principal_client.get(reverse("orders:register")).content.decode()
    second = issue_order(faculty=other_faculty, committee=exam_committee)
    cancel_order(order=second, reason="Test correction.", issued_by=principal)
    with CaptureQueriesContext(connection) as larger:
        assert escape(other_faculty.full_name) in principal_client.get(reverse("orders:register")).content.decode()
    assert len(larger) == len(small)
