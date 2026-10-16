"""
The permission matrix from docs/03_SECURITY.md §2, plus the completeness test
that fails when a new endpoint ships without a permission decision.
"""

import pytest
from django.urls import URLResolver, get_resolver, reverse

from assignments.models import Assignment

pytestmark = pytest.mark.django_db

REDIRECT = "redirect"

# (url name, kwargs source, anonymous, faculty, principal)
MATRIX = [
    ("core:index", None, 200, REDIRECT, REDIRECT),
    ("accounts:login", None, 200, REDIRECT, REDIRECT),
    ("accounts:logout", None, 405, 405, 405),
    ("accounts:profile", None, REDIRECT, 200, 200),
    ("accounts:workload", None, REDIRECT, 200, 200),
    ("accounts:faculty_list", None, REDIRECT, 403, 200),
    ("accounts:faculty_create", None, REDIRECT, 403, 200),
    ("accounts:faculty_detail", "faculty_pk", REDIRECT, 403, 200),
    ("accounts:faculty_edit", "faculty_pk", REDIRECT, 403, 200),
    ("accounts:faculty_deactivate", "faculty_pk", REDIRECT, 403, 200),
    ("assignments:dashboard", None, REDIRECT, 200, 200),
    ("assignments:directory", None, REDIRECT, 200, 200),
    ("committees:list", None, REDIRECT, 200, 200),
    ("committees:detail", "committee_pk", REDIRECT, 200, 200),
    ("committees:create", None, REDIRECT, 403, 200),
    ("committees:edit", "committee_pk", REDIRECT, 403, 200),
    ("orders:assign", None, REDIRECT, 403, 200),
    ("orders:register", None, REDIRECT, 403, 200),
    ("orders:detail", "order_pk", REDIRECT, 404, 200),
    ("orders:download", "order_pk", REDIRECT, 404, 200),
    ("orders:cancel", "order_pk", REDIRECT, 403, 200),
    ("orders:relinquish", "assignment_pk", REDIRECT, 403, 200),
]

# Reachable without signing in, by design: the landing page and the sign-in page.
DOCUMENTED_EXEMPTIONS = {"core:index", "accounts:login"}


@pytest.fixture
def scenario(principal, other_faculty, committee, issue_order):
    """An order belonging to someone other than the `faculty` fixture."""
    order = issue_order(faculty=other_faculty, committee=committee)
    return {
        "faculty_pk": {"pk": other_faculty.pk},
        "committee_pk": {"pk": committee.pk},
        "order_pk": {"pk": order.pk},
        "assignment_pk": {"pk": Assignment.objects.get().pk},
    }


def check(response, expected):
    if expected == REDIRECT:
        assert response.status_code in (301, 302), f"expected a redirect, got {response.status_code}"
    else:
        assert response.status_code == expected


@pytest.mark.parametrize("name,kwargs_key,anon,faculty_code,principal_code", MATRIX)
def test_permission_matrix(
    client, faculty, principal, scenario, name, kwargs_key, anon, faculty_code, principal_code
):
    url = reverse(name, kwargs=scenario[kwargs_key] if kwargs_key else None)

    check(client.get(url), anon)

    client.force_login(faculty)
    check(client.get(url), faculty_code)

    client.logout()
    client.force_login(principal)
    check(client.get(url), principal_code)


def collect_url_names():
    names = set()
    for entry in get_resolver().url_patterns:
        if isinstance(entry, URLResolver) and entry.namespace != "admin":
            names |= {f"{entry.namespace}:{p.name}" for p in entry.url_patterns}
    return names


def test_every_endpoint_appears_in_the_matrix():
    """Fails when an endpoint is added without deciding who may reach it."""
    tested = {row[0] for row in MATRIX}
    assert collect_url_names() - tested == set()


def test_no_endpoint_serves_an_anonymous_visitor(client, scenario):
    """Every URL except the documented two must refuse anonymous access."""
    served = []
    for name in collect_url_names() - DOCUMENTED_EXEMPTIONS:
        kwargs = next(
            (scenario[row[1]] for row in MATRIX if row[0] == name and row[1]), None
        )
        if client.get(reverse(name, kwargs=kwargs)).status_code == 200:
            served.append(name)
    assert served == []


def test_a_faculty_member_cannot_read_another_persons_order(
    client, faculty, other_faculty, committee, issue_order
):
    order = issue_order(faculty=other_faculty, committee=committee)
    client.force_login(faculty)
    assert client.get(reverse("orders:detail", kwargs={"pk": order.pk})).status_code == 404
    assert client.get(reverse("orders:download", kwargs={"pk": order.pk})).status_code == 404


def test_the_owner_can_read_and_download_their_own_order(
    client, faculty, committee, issue_order
):
    order = issue_order(faculty=faculty, committee=committee)
    client.force_login(faculty)
    assert client.get(reverse("orders:detail", kwargs={"pk": order.pk})).status_code == 200
    response = client.get(reverse("orders:download", kwargs={"pk": order.pk}))
    assert response.status_code == 200
    assert response["Content-Disposition"].startswith("attachment;")
    assert response["Cache-Control"] == "private, no-store"


def test_an_order_file_is_not_served_from_the_media_url(
    client, principal, faculty, committee, issue_order
):
    order = issue_order(faculty=faculty, committee=committee)
    client.force_login(principal)
    assert client.get(f"/media/{order.generated_file.name}").status_code == 404


def test_write_endpoints_reject_a_post_without_a_csrf_token(
    principal, faculty, committee, issue_order
):
    from django.test import Client

    order = issue_order(faculty=faculty, committee=committee)
    client = Client(enforce_csrf_checks=True)
    client.force_login(principal)
    for url, payload in [
        (reverse("orders:assign"), {"step": "preview"}),
        (reverse("orders:cancel", kwargs={"pk": order.pk}), {"reason": "Issued in error."}),
        (reverse("accounts:profile"), {"mobile": "9876543210"}),
    ]:
        assert client.post(url, payload).status_code == 403, url
