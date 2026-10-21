"""Principal staff search must preserve counts, visibility and membership history."""

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils.html import escape

from accounts.models import User
from assignments.models import AssignmentRole

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("query", ["faculty one", "  FACULTY ONE  "])
def test_search_matches_partial_name_without_case_or_surrounding_space(
    principal_client, faculty, other_faculty, query
):
    response = principal_client.get(reverse("accounts:faculty_list"), {"q": query})
    assert [person.pk for person in response.context["people"]] == [faculty.pk]


@pytest.mark.parametrize("query", ["computer", "co", "COMPUTER ENGINEERING", "placement", "tpu"])
def test_search_does_not_match_departments_or_committees(
    principal_client, faculty, committee, issue_order, query
):
    issue_order(faculty=faculty, committee=committee)
    response = principal_client.get(reverse("accounts:faculty_list"), {"q": query})
    assert response.context["people"] == []


def test_name_search_keeps_full_counts_without_duplicate_people(
    principal_client, faculty, other_faculty, committee, exam_committee, issue_order
):
    issue_order(faculty=faculty, committee=committee)
    issue_order(faculty=faculty, committee=committee, role=AssignmentRole.MEMBER)
    issue_order(faculty=faculty, committee=exam_committee, role=AssignmentRole.MEMBER)
    response = principal_client.get(reverse("accounts:faculty_list"), {"q": "Faculty One"})
    people = response.context["people"]
    assert [(person.pk, person.active_count) for person in people] == [(faculty.pk, 3)]


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


def test_name_search_handles_a_holder_without_a_department(
    principal_client, faculty, committee, issue_order
):
    faculty.department = None
    faculty.save(update_fields=["department"])
    issue_order(faculty=faculty, committee=committee)
    response = principal_client.get(reverse("accounts:faculty_list"), {"q": "Faculty One"})
    assert [person.pk for person in response.context["people"]] == [faculty.pk]


def test_search_queries_do_not_grow_with_the_number_of_results(
    principal_client, faculty, other_faculty, committee, issue_order
):
    url = reverse("accounts:faculty_list")
    issue_order(faculty=faculty, committee=committee, role=AssignmentRole.MEMBER)
    with CaptureQueriesContext(connection) as small:
        assert len(principal_client.get(url, {"q": "Faculty One"}).context["people"]) == 1
    issue_order(faculty=other_faculty, committee=committee, role=AssignmentRole.MEMBER)
    with CaptureQueriesContext(connection) as larger:
        people = principal_client.get(url, {"q": "Faculty"}).context["people"]
        assert {person.pk for person in people} == {faculty.pk, other_faculty.pk}
    assert len(larger) == len(small)


def test_a_name_that_matches_a_department_code_still_matches_by_name(principal_client, faculty):
    faculty.full_name = "Test Cooper"
    faculty.save(update_fields=["full_name"])
    response = principal_client.get(reverse("accounts:faculty_list"), {"q": "co"})
    assert [person.pk for person in response.context["people"]] == [faculty.pk]
