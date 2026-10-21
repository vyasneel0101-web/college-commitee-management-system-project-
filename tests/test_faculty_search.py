"""Principal staff search must preserve counts, visibility and membership history."""

from datetime import date

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils.html import escape

from accounts.models import Department, User
from assignments.models import AssignmentRole
from orders.services import issue_relinquishment_order

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("query", ["faculty one", "  FACULTY ONE  "])
def test_search_matches_partial_name_without_case_or_surrounding_space(
    principal_client, faculty, other_faculty, query
):
    response = principal_client.get(reverse("accounts:faculty_list"), {"q": query})
    assert [person.pk for person in response.context["people"]] == [faculty.pk]


@pytest.mark.parametrize("query", ["computer", "co", "COMPUTER ENGINEERING"])
def test_search_matches_department_name_and_code(principal_client, faculty, other_faculty, query):
    other_department = Department.objects.create(code="ME", name="Mechanical Engineering")
    other_faculty.department = other_department
    other_faculty.save(update_fields=["department"])
    response = principal_client.get(reverse("accounts:faculty_list"), {"q": query})
    assert [person.pk for person in response.context["people"]] == [faculty.pk]


@pytest.mark.parametrize("query", ["placement", "tpu"])
def test_committee_search_matches_current_holders_and_keeps_full_counts(
    principal_client, faculty, other_faculty, committee, exam_committee, issue_order, query
):
    issue_order(faculty=faculty, committee=committee)
    issue_order(faculty=faculty, committee=committee, role=AssignmentRole.MEMBER)
    issue_order(faculty=faculty, committee=exam_committee, role=AssignmentRole.MEMBER)
    response = principal_client.get(reverse("accounts:faculty_list"), {"q": query})
    people = response.context["people"]
    assert [(person.pk, person.active_count) for person in people] == [(faculty.pk, 3)]


def test_committee_search_excludes_superseded_and_relinquished_members(
    principal_client, principal, faculty, other_faculty, third_faculty, committee, issue_order
):
    issue_order(faculty=faculty, committee=committee)
    issue_order(faculty=other_faculty, committee=committee, order_date=date(2026, 8, 1))
    member = issue_order(
        faculty=third_faculty, committee=committee, role=AssignmentRole.MEMBER
    ).created_assignments.get()
    issue_relinquishment_order(assignment=member, order_date=date(2026, 8, 2), issued_by=principal)
    response = principal_client.get(reverse("accounts:faculty_list"), {"q": committee.code})
    assert [person.pk for person in response.context["people"]] == [other_faculty.pk]


def test_search_keeps_deactivated_staff_and_excludes_technical_superusers(
    principal_client, faculty, other_faculty
):
    faculty.is_active = False
    faculty.save(update_fields=["is_active"])
    User.objects.create_superuser(email="test-admin@example.invalid", full_name="Test Faculty Admin")
    response = principal_client.get(reverse("accounts:faculty_list"), {"q": "Faculty"})
    assert {person.pk for person in response.context["people"]} == {faculty.pk, other_faculty.pk}
    assert "Deactivated" in response.content.decode()


def test_empty_search_preserves_the_full_staff_list(principal_client, faculty, other_faculty):
    url = reverse("accounts:faculty_list")
    original = [person.pk for person in principal_client.get(url).context["people"]]
    cleared = principal_client.get(url, {"q": "  "})
    assert [person.pk for person in cleared.context["people"]] == original


def test_no_matches_shows_an_empty_message_and_escapes_the_query(principal_client, faculty):
    query = '<script>alert("test")</script>'
    response = principal_client.get(reverse("accounts:faculty_list"), {"q": query})
    html = response.content.decode()
    assert response.context["people"] == []
    assert "No staff match" in html and "Clear search" in html
    assert escape(query) in html and query not in html


def test_overlong_search_has_a_visible_validation_error(principal_client, faculty):
    response = principal_client.get(reverse("accounts:faculty_list"), {"q": "x" * 101})
    assert "q" in response.context["form"].errors
    assert 'id="faculty-search-error"' in response.content.decode()


def test_search_stays_principal_only(client, faculty):
    url = reverse("accounts:faculty_list")
    anonymous = client.get(url, {"q": "Faculty"})
    assert anonymous.status_code == 302 and "/login/" in anonymous.url
    client.force_login(faculty)
    response = client.get(url, {"q": "Faculty"})
    assert response.status_code == 403
    assert "faculty.one@test.local" not in response.content.decode()


def test_committee_search_handles_a_holder_without_a_department(
    principal_client, faculty, committee, issue_order
):
    faculty.department = None
    faculty.save(update_fields=["department"])
    issue_order(faculty=faculty, committee=committee)
    response = principal_client.get(reverse("accounts:faculty_list"), {"q": committee.code})
    assert [person.pk for person in response.context["people"]] == [faculty.pk]


def test_search_queries_do_not_grow_with_the_number_of_results(
    principal_client, faculty, other_faculty, committee, issue_order
):
    url = reverse("accounts:faculty_list")
    issue_order(faculty=faculty, committee=committee, role=AssignmentRole.MEMBER)
    with CaptureQueriesContext(connection) as small:
        assert len(principal_client.get(url, {"q": committee.code}).context["people"]) == 1
    issue_order(faculty=other_faculty, committee=committee, role=AssignmentRole.MEMBER)
    with CaptureQueriesContext(connection) as larger:
        people = principal_client.get(url, {"q": committee.code}).context["people"]
        assert {person.pk for person in people} == {faculty.pk, other_faculty.pk}
    assert len(larger) == len(small)


def test_exact_department_code_does_not_match_the_word_committee(
    principal_client, faculty, other_faculty, exam_committee, issue_order
):
    mechanical = Department.objects.create(code="ME", name="Mechanical Engineering")
    other_faculty.department = mechanical
    other_faculty.save(update_fields=["department"])
    issue_order(faculty=other_faculty, committee=exam_committee)
    response = principal_client.get(reverse("accounts:faculty_list"), {"q": "co"})
    assert [person.pk for person in response.context["people"]] == [faculty.pk]
