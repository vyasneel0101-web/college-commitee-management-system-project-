"""
Fixtures for the suite.

Everything is built through the real services wherever an order is involved,
so a test that passes is evidence the pipeline works, not just the model.
"""

from datetime import date

import pytest
from django.conf import settings
from django.core.files import File

from accounts.models import Department, Designation, GovtClass, Role, User
from assignments.models import AssignmentRole
from committees.models import Committee
from core.models import AcademicYear
from orders.services import issue_assignment_order

FIXTURE_DIR = "tests/fixtures"
ORDER_DATE = date(2026, 7, 1)


@pytest.fixture
def department(db):
    return Department.objects.create(code="CO", name="Computer Engineering")


@pytest.fixture
def year(db):
    AcademicYear.objects.create(
        label="2025-26", start_date=date(2025, 6, 1), end_date=date(2026, 5, 31)
    )
    return AcademicYear.objects.create(
        label="2026-27",
        start_date=date(2026, 6, 1),
        end_date=date(2027, 5, 31),
        is_current=True,
    )


@pytest.fixture
def last_year(db, year):
    return AcademicYear.objects.get(label="2025-26")


def _make_user(email, name, role=Role.FACULTY, department=None, **extra):
    user = User.objects.create_user(
        email=email,
        password="pw-for-tests-only",
        full_name=name,
        salutation="Shri",
        designation=extra.pop("designation", Designation.LECTURER),
        govt_class=GovtClass.CLASS_II,
        department=department,
        **extra,
    )
    if role != Role.FACULTY:
        user.role = role
        user.save(update_fields=["role"])
    return user


@pytest.fixture
def principal(db, department):
    person = _make_user(
        "principal@test.local",
        "Test Principal One",
        role=Role.PRINCIPAL,
        designation=Designation.PRINCIPAL,
    )
    signature = settings.BASE_DIR / "templates" / "demo" / "demo_principal_signature.png"
    with signature.open("rb") as handle:
        person.signature_image.save("sig.png", File(handle), save=True)
    return person


@pytest.fixture
def faculty(db, department):
    return _make_user("faculty.one@test.local", "Test Faculty One", department=department)


@pytest.fixture
def other_faculty(db, department):
    return _make_user("faculty.two@test.local", "Test Faculty Two", department=department)


@pytest.fixture
def third_faculty(db, department):
    return _make_user("faculty.three@test.local", "Test Faculty Three", department=department)


def _committee(code, name, principal=None, *, allows_multiple_members=True):
    return Committee.objects.create(
        code=code, name=name, allows_multiple_members=allows_multiple_members
    )


@pytest.fixture(autouse=True)
def order_template(db):
    """The one template every order uses, installed as it would be at setup."""
    from orders.order_template import install_order_template

    source = settings.BASE_DIR / "tests" / "fixtures" / "order_template.docx"
    with source.open("rb") as handle:
        return install_order_template(File(handle, name="order_template.docx"))


@pytest.fixture
def committee(db, principal):
    return _committee("TPU", "Training & Placement Unit", principal)


@pytest.fixture
def exam_committee(db, principal):
    return _committee("EXAM", "Examination Committee", principal)


@pytest.fixture
def table_committee(db, principal):
    """A committee whose template prints a table of everyone appointed."""
    return _committee(
        "ICC", "Internal Complaint Committee", principal
    )


@pytest.fixture
def lead_only_committee(db, principal):
    return _committee(
        "ALM", "Alumni Association Cell", principal, allows_multiple_members=False
    )


@pytest.fixture
def issue_order(db, principal, year):
    """Issue an assignment order through the real service."""

    def _issue(
        *,
        committee,
        faculty=None,
        role=AssignmentRole.PRESIDING_OFFICER,
        appointments=None,
        order_date=ORDER_DATE,
        **kwargs,
    ):
        return issue_assignment_order(
            committee=committee,
            appointments=appointments or [(faculty, role)],
            order_date=order_date,
            issued_by=principal,
            **kwargs,
        )

    return _issue


@pytest.fixture
def external_member(db):
    from accounts.models import ExternalMember

    return ExternalMember.objects.create(
        salutation="Ms.",
        full_name="Test External One",
        organisation="Example Welfare Organisation",
    )


@pytest.fixture
def principal_client(client, principal):
    client.force_login(principal)
    return client


@pytest.fixture
def faculty_client(client, faculty):
    client.force_login(faculty)
    return client
