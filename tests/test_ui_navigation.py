"""Presentation regressions: role-aware navigation and labelled form controls."""

from html.parser import HTMLParser
import re

import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db


class Elements(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.tags = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


def sidebar_links(response):
    html = response.content.decode()
    sidebar = re.search(r'<aside\b.*?</aside>', html, re.S).group(0)
    return [attrs for tag, attrs in Elements(sidebar).tags if tag == "a"]


def test_faculty_navigation_keeps_management_actions_private(faculty_client):
    links = sidebar_links(faculty_client.get(reverse("assignments:dashboard")))
    destinations = {link["href"] for link in links}
    for name in ("accounts:faculty_list", "accounts:workload", "orders:register", "orders:assign"):
        assert reverse(name) not in destinations
    for name in ("assignments:directory", "committees:list", "accounts:profile"):
        assert reverse(name) in destinations


@pytest.mark.parametrize(
    "page,parent",
    [
        ("accounts:faculty_create", "accounts:faculty_list"),
        ("committees:create", "committees:list"),
        ("orders:assign", "orders:assign"),
    ],
)
def test_management_forms_keep_their_section_selected(principal_client, page, parent):
    links = sidebar_links(principal_client.get(reverse(page)))
    current = [link["href"] for link in links if link.get("aria-current") == "page"]
    assert current == [reverse(parent)]


def test_assignment_rows_have_unique_ids_and_matching_labels(principal_client):
    html = principal_client.get(reverse("orders:assign")).content.decode()
    elements = Elements(html).tags
    selects = [attrs for tag, attrs in elements if tag == "select" and attrs.get("name", "").startswith("form-")]
    labels = {attrs.get("for") for tag, attrs in elements if tag == "label"}
    ids = [attrs["id"] for attrs in selects]
    assert len(ids) == len(set(ids))
    assert set(ids) <= labels
    assert {attrs["name"] for attrs in selects} >= {"form-0-person", "form-0-role", "form-__prefix__-person", "form-__prefix__-role"}
    hidden = {attrs.get("name") for tag, attrs in elements if tag == "input" and attrs.get("type") == "hidden"}
    assert {"csrfmiddlewaretoken", "step", "form-TOTAL_FORMS", "form-INITIAL_FORMS"} <= hidden
