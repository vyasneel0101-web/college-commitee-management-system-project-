"""
Screens and flows: what each page shows, and what a form will and will not write.
"""

import re
from datetime import date, timedelta

import pytest
from django.urls import reverse
from django.utils.html import escape
from django.utils import timezone

from accounts.models import Designation, Role
from assignments.models import Assignment, AssignmentRole, AssignmentStatus
from orders.models import Order

pytestmark = pytest.mark.django_db


def select_block(html, name):
    match = re.search(r'<select[^>]*name="%s".*?</select>' % name, html, re.S)
    assert match, f"no <select name={name}> on the page"
    return match.group(0)


class TestDashboard:
    def test_it_shows_only_your_own_committees(
        self, client, faculty, other_faculty, committee, exam_committee, issue_order
    ):
        issue_order(faculty=faculty, committee=committee)
        issue_order(faculty=other_faculty, committee=exam_committee)
        client.force_login(faculty)
        html = client.get(reverse("assignments:dashboard")).content.decode()
        assert escape(committee.name) in html
        assert escape(exam_committee.name) not in html

    def test_a_superseded_committee_moves_to_the_past_list(
        self, client, faculty, other_faculty, committee, issue_order
    ):
        issue_order(faculty=faculty, committee=committee)
        issue_order(faculty=other_faculty, committee=committee, order_date=date(2026, 8, 1))
        client.force_login(faculty)
        html = client.get(reverse("assignments:dashboard")).content.decode()
        assert "Past committees" in html
        assert other_faculty.full_name in html  # "Handed to ..."
        assert "pill-history" in html

    def test_someone_with_nothing_sees_the_empty_state(self, client, faculty):
        client.force_login(faculty)
        html = client.get(reverse("assignments:dashboard")).content.decode()
        assert "You currently hold no committees" in html


class TestDirectory:
    def test_it_lists_active_assignments_only(
        self, client, faculty, other_faculty, committee, issue_order
    ):
        issue_order(faculty=faculty, committee=committee)
        issue_order(faculty=other_faculty, committee=committee, order_date=date(2026, 8, 1))
        client.force_login(faculty)
        html = client.get(reverse("assignments:directory")).content.decode()
        body = html.split("<tbody>", 1)[1]
        assert other_faculty.full_name in body
        assert faculty.full_name not in body

    def test_the_filter_narrows_by_committee_code(
        self, client, faculty, other_faculty, committee, exam_committee, issue_order
    ):
        issue_order(faculty=faculty, committee=committee)
        issue_order(faculty=other_faculty, committee=exam_committee)
        client.force_login(faculty)
        html = client.get(reverse("assignments:directory"), {"q": "EXAM"}).content.decode()
        assert html.split("<tbody>", 1)[1].count('data-label="Committee"') == 1

    def test_a_filter_with_no_matches_explains_itself(self, client, faculty):
        client.force_login(faculty)
        html = client.get(reverse("assignments:directory"), {"q": "zzzz"}).content.decode()
        assert "No active assignments match" in html


class TestWorkload:
    def test_it_sorts_by_committees_held(
        self, client, faculty, other_faculty, committee, exam_committee, issue_order
    ):
        issue_order(faculty=faculty, committee=committee)
        issue_order(faculty=faculty, committee=exam_committee, order_date=date(2026, 7, 2))
        issue_order(
            faculty=other_faculty,
            committee=committee,
            role=AssignmentRole.MEMBER,
            order_date=date(2026, 7, 3),
        )
        client.force_login(faculty)
        html = client.get(reverse("accounts:workload")).content.decode()
        assert html.index(faculty.full_name) < html.index(other_faculty.full_name)

    def test_it_never_shows_contact_details(
        self, client, faculty, other_faculty, committee, issue_order
    ):
        other_faculty.mobile = "+919000000001"
        other_faculty.save(update_fields=["mobile"])
        issue_order(faculty=other_faculty, committee=committee)
        client.force_login(faculty)
        html = client.get(reverse("accounts:workload")).content.decode()
        assert "+919000000001" not in html
        assert other_faculty.email not in html


class TestProfile:
    def test_the_mobile_number_can_be_changed(self, client, faculty):
        client.force_login(faculty)
        client.post(reverse("accounts:profile"), {"mobile": "+919876543210"})
        faculty.refresh_from_db()
        assert faculty.mobile == "+919876543210"

    def test_an_invalid_number_is_rejected(self, client, faculty):
        client.force_login(faculty)
        response = client.post(reverse("accounts:profile"), {"mobile": "12345"})
        faculty.refresh_from_db()
        assert "Enter a 10-digit mobile number" in response.content.decode()
        assert faculty.mobile != "12345"

    def test_posting_a_role_or_status_changes_nothing(self, client, faculty, department):
        """The most valuable security test in the project (T2)."""
        client.force_login(faculty)
        before = {
            field: getattr(faculty, field)
            for field in ("role", "is_active", "is_staff", "is_superuser", "designation", "email", "full_name")
        }
        client.post(
            reverse("accounts:profile"),
            {
                "mobile": "+919876543210",
                "role": Role.PRINCIPAL,
                "is_active": "False",
                "is_staff": "on",
                "is_superuser": "on",
                "designation": Designation.PRINCIPAL,
                "email": "attacker@evil.example.com",
                "full_name": "Someone Else",
            },
        )
        faculty.refresh_from_db()
        assert {field: getattr(faculty, field) for field in before} == before


class TestAssignFlow:
    def test_the_faculty_dropdown_offers_an_explicit_empty_choice(
        self, principal_client, faculty, committee
    ):
        """Nobody must be pre-selected: the browser would otherwise pick the first person."""
        html = principal_client.get(reverse("orders:assign")).content.decode()
        block = select_block(html, "faculty")
        assert 'value="" selected' in block
        assert "Choose a faculty member" in block

    def test_each_name_shows_the_committee_count(
        self, principal_client, faculty, committee, issue_order
    ):
        issue_order(faculty=faculty, committee=committee)
        html = principal_client.get(reverse("orders:assign")).content.decode()
        assert f"{faculty.full_name} · CO · 1 active committee" in html

    def test_submitting_without_a_faculty_member_is_refused(
        self, principal_client, committee, year
    ):
        response = principal_client.post(
            reverse("orders:assign"),
            {
                "committee": committee.pk,
                "faculty": "",
                "role": AssignmentRole.CONVENER,
                "order_date": date(2026, 7, 1).isoformat(),
                "step": "preview",
            },
        )
        assert response.status_code == 200
        assert "This field is required." in response.content.decode()
        assert Order.objects.count() == 0

    def test_a_choice_survives_a_validation_error(
        self, principal_client, faculty, committee
    ):
        response = principal_client.post(
            reverse("orders:assign"),
            {
                "committee": committee.pk,
                "faculty": faculty.pk,
                "order_date": date(2026, 7, 1).isoformat(),
                "step": "preview",
            },
        )
        block = select_block(response.content.decode(), "faculty")
        assert f'value="{faculty.pk}" selected' in block

    def test_the_preview_states_what_will_happen_and_writes_nothing(
        self, principal_client, faculty, other_faculty, committee, issue_order
    ):
        issue_order(faculty=faculty, committee=committee)
        before = (Order.objects.count(), Assignment.objects.count())
        response = principal_client.post(
            reverse("orders:assign"),
            {
                "committee": committee.pk,
                "faculty": other_faculty.pk,
                "role": AssignmentRole.CONVENER,
                "order_date": date(2026, 8, 1).isoformat(),
                "step": "preview",
            },
        )
        html = response.content.decode()
        assert "Issue order" in html
        assert faculty.full_name in html  # the holder who would be superseded
        assert (Order.objects.count(), Assignment.objects.count()) == before

    def test_issuing_creates_the_order_and_the_assignment(
        self, principal_client, faculty, committee, year
    ):
        response = principal_client.post(
            reverse("orders:assign"),
            {
                "committee": committee.pk,
                "faculty": faculty.pk,
                "role": AssignmentRole.CONVENER,
                "order_date": date(2026, 7, 1).isoformat(),
                "step": "issue",
                "expected_superseded": "none",
            },
        )
        order = Order.objects.get()
        assert response.status_code == 302
        assert response["Location"] == reverse("orders:detail", kwargs={"pk": order.pk})
        assert order.created_assignments.get().faculty == faculty

    def test_issuing_without_a_preview_is_refused(
        self, principal_client, faculty, committee, year
    ):
        response = principal_client.post(
            reverse("orders:assign"),
            {
                "committee": committee.pk,
                "faculty": faculty.pk,
                "role": AssignmentRole.CONVENER,
                "order_date": date(2026, 7, 1).isoformat(),
                "step": "issue",
            },
        )
        assert "previewed" in response.content.decode()
        assert Order.objects.count() == 0

    def test_a_future_date_is_refused_with_a_readable_message(
        self, principal_client, faculty, committee, year
    ):
        response = principal_client.post(
            reverse("orders:assign"),
            {
                "committee": committee.pk,
                "faculty": faculty.pk,
                "role": AssignmentRole.CONVENER,
                "order_date": (timezone.localdate() + timedelta(days=1)).isoformat(),
                "step": "preview",
            },
        )
        assert "cannot be in the future" in response.content.decode()


class TestFacultyManagement:
    def test_a_new_record_is_always_created_as_faculty(self, principal_client, department):
        principal_client.post(
            reverse("accounts:faculty_create"),
            {
                "salutation": "Shri",
                "full_name": "Test Faculty Nine",
                "email": "New.Person@test.local",
                "designation": Designation.LECTURER,
                "govt_class": "CLASS_II",
                "department": department.pk,
                "employee_code": "",
                "joining_date": "",
                "mobile": "",
                "role": Role.PRINCIPAL,
                "is_staff": "on",
                "is_superuser": "on",
            },
        )
        from accounts.models import User

        person = User.objects.get(email="new.person@test.local")
        assert person.role == Role.FACULTY
        assert not person.is_staff and not person.is_superuser

    def test_deactivation_does_not_end_committees(
        self, principal_client, faculty, committee, issue_order
    ):
        issue_order(faculty=faculty, committee=committee)
        response = principal_client.post(
            reverse("accounts:faculty_deactivate", kwargs={"pk": faculty.pk}),
            {"confirm": "on"},
        )
        faculty.refresh_from_db()
        assert response.status_code == 302
        assert not faculty.is_active
        assert Assignment.objects.active().filter(faculty=faculty).count() == 1

    def test_the_deactivation_page_warns_about_committees_held(
        self, principal_client, faculty, committee, issue_order
    ):
        issue_order(faculty=faculty, committee=committee)
        html = principal_client.get(
            reverse("accounts:faculty_deactivate", kwargs={"pk": faculty.pk})
        ).content.decode()
        assert "still holds" in html and escape(committee.name) in html


class TestCommitteeManagement:
    def test_a_lowercase_code_is_corrected_rather_than_refused(self, principal_client):
        principal_client.post(
            reverse("committees:create"),
            {"name": "Test Committee One", "code": "tst", "allows_multiple_members": "on", "is_active": "on"},
        )
        from committees.models import Committee

        assert Committee.objects.get(name="Test Committee One").code == "TST"

    def test_the_code_cannot_change_once_an_order_exists(
        self, principal_client, faculty, committee, issue_order
    ):
        issue_order(faculty=faculty, committee=committee)
        principal_client.post(
            reverse("committees:edit", kwargs={"pk": committee.pk}),
            {"name": committee.name, "code": "HACKED", "allows_multiple_members": "on", "is_active": "on"},
        )
        committee.refresh_from_db()
        assert committee.code == "TPU"


class TestTemplateUpload:
    def _upload(self, client, committee, name, content):
        from django.core.files.uploadedfile import SimpleUploadedFile

        return client.post(
            reverse("committees:template", kwargs={"pk": committee.pk}),
            {"docx_file": SimpleUploadedFile(name, content)},
        )

    def test_a_macro_enabled_file_is_rejected(self, principal_client, committee):
        from django.conf import settings

        source = settings.BASE_DIR / "tests" / "fixtures" / "order_template_TPU.docx"
        response = self._upload(principal_client, committee, "t.docm", source.read_bytes())
        assert "Only .docx files are accepted" in response.content.decode()
        assert committee.templates.count() == 1

    def test_a_file_that_is_not_a_document_is_rejected(self, principal_client, committee):
        response = self._upload(principal_client, committee, "t.docx", b"not a zip at all")
        assert "not a valid Word document" in response.content.decode()
        assert committee.templates.count() == 1

    def test_a_template_missing_placeholders_names_them(self, principal_client, committee):
        import io

        from docx import Document

        document = Document()
        document.add_paragraph("Nothing useful here.")
        buffer = io.BytesIO()
        document.save(buffer)
        response = self._upload(principal_client, committee, "bare.docx", buffer.getvalue())
        body = response.content.decode()
        assert "missing" in body and "order_no" in body
        assert committee.templates.count() == 1

    def test_a_valid_upload_supersedes_the_previous_version(
        self, principal_client, committee
    ):
        from django.conf import settings

        source = settings.BASE_DIR / "tests" / "fixtures" / "order_template_EXAM.docx"
        self._upload(principal_client, committee, "v2.docx", source.read_bytes())
        assert committee.templates.count() == 2
        assert committee.templates.filter(is_active=True).count() == 1
        assert committee.templates.order_by("-version").first().version == 2


class TestAuditLogScreen:
    def test_it_shows_readable_action_names(
        self, principal_client, faculty, committee, issue_order
    ):
        issue_order(faculty=faculty, committee=committee)
        html = principal_client.get(reverse("audit:log")).content.decode()
        body = html.split("<tbody>", 1)[1]
        assert "Order issued" in body
        assert "ORDER_ISSUED" not in body

    def test_it_can_be_filtered_by_action(
        self, principal_client, faculty, committee, issue_order
    ):
        issue_order(faculty=faculty, committee=committee)
        html = principal_client.get(reverse("audit:log"), {"action": "ORDER_ISSUED"}).content.decode()
        body = html.split("<tbody>", 1)[1]
        assert body.count('data-label="When"') == 1


class TestSignIn:
    def test_the_address_may_be_typed_in_any_case(self, client, faculty):
        faculty.set_password("demo-password")
        faculty.save(update_fields=["password"])
        response = client.post(
            reverse("accounts:login"),
            {"username": "FACULTY.ONE@TEST.LOCAL", "password": "demo-password"},
        )
        assert response.status_code == 302

    def test_a_wrong_password_is_reported_clearly(self, client, faculty):
        response = client.post(
            reverse("accounts:login"),
            {"username": faculty.email, "password": "wrong"},
        )
        assert "not correct" in response.content.decode()

    def test_an_off_site_next_is_ignored(self, client, faculty):
        faculty.set_password("demo-password")
        faculty.save(update_fields=["password"])
        response = client.post(
            reverse("accounts:login"),
            {
                "username": faculty.email,
                "password": "demo-password",
                "next": "https://evil.example.com/",
            },
        )
        assert response["Location"] == reverse("assignments:dashboard")

    def test_a_deactivated_person_cannot_sign_in(self, client, faculty):
        faculty.set_password("demo-password")
        faculty.is_active = False
        faculty.save(update_fields=["password", "is_active"])
        response = client.post(
            reverse("accounts:login"),
            {"username": faculty.email, "password": "demo-password"},
        )
        assert response.status_code == 200
