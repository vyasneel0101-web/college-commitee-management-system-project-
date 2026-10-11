"""Model layer: constraints, immutability and managers. docs/05_TESTING.md §2."""

from datetime import date

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from accounts.models import Designation, GovtClass, Role, User
from assignments.models import Assignment, AssignmentRole, AssignmentStatus
from audit.models import AuditAction, AuditLogEntry
from core.exceptions import NoCurrentAcademicYear, RecordImmutable
from core.models import AcademicYear

pytestmark = pytest.mark.django_db


def make_assignment(faculty, committee, order, role=AssignmentRole.CONVENER, **kwargs):
    """Create a row directly, to test what the database itself refuses."""
    return Assignment.objects.create(
        faculty=faculty,
        committee=committee,
        role=role,
        academic_year=order.academic_year,
        status=kwargs.pop("status", AssignmentStatus.ACTIVE),
        start_date=kwargs.pop("start_date", order.order_date),
        issuing_order=order,
        **kwargs,
    )


class TestAssignmentConstraints:
    def test_same_faculty_committee_and_role_cannot_both_be_active(
        self, faculty, committee, issue_order
    ):
        order = issue_order(faculty=faculty, committee=committee)
        with pytest.raises(IntegrityError), transaction.atomic():
            make_assignment(faculty, committee, order)

    def test_two_active_conveners_in_one_committee_are_refused(
        self, faculty, other_faculty, committee, issue_order
    ):
        order = issue_order(faculty=faculty, committee=committee)
        with pytest.raises(IntegrityError), transaction.atomic():
            make_assignment(other_faculty, committee, order)

    def test_same_faculty_may_convene_two_different_committees(
        self, faculty, committee, exam_committee, issue_order
    ):
        issue_order(faculty=faculty, committee=committee)
        issue_order(faculty=faculty, committee=exam_committee, order_date=date(2026, 7, 2))
        assert Assignment.objects.active().filter(faculty=faculty).count() == 2

    def test_superseded_row_may_coexist_with_an_active_one(
        self, faculty, other_faculty, committee, issue_order
    ):
        issue_order(faculty=faculty, committee=committee)
        issue_order(faculty=other_faculty, committee=committee, order_date=date(2026, 7, 5))
        rows = Assignment.objects.filter(committee=committee, role=AssignmentRole.CONVENER)
        assert rows.count() == 2
        assert rows.filter(status=AssignmentStatus.ACTIVE).count() == 1

    def test_active_assignment_cannot_carry_an_end_date(self, faculty, committee, issue_order):
        order = issue_order(faculty=faculty, committee=committee)
        assignment = order.created_assignments.get()
        assignment.end_date = date(2026, 8, 1)
        with pytest.raises(IntegrityError), transaction.atomic():
            assignment.save(update_fields=["end_date"])

    def test_end_date_cannot_precede_start_date(self, faculty, committee, issue_order):
        order = issue_order(faculty=faculty, committee=committee)
        with pytest.raises(IntegrityError), transaction.atomic():
            make_assignment(
                faculty,
                committee,
                order,
                role=AssignmentRole.MEMBER,
                status=AssignmentStatus.EXPIRED,
                start_date=date(2026, 7, 10),
                end_date=date(2026, 7, 1),
            )


class TestAcademicYear:
    def test_only_one_year_can_be_current(self, year):
        with pytest.raises(IntegrityError), transaction.atomic():
            AcademicYear.objects.create(
                label="2027-28",
                start_date=date(2027, 6, 1),
                end_date=date(2028, 5, 31),
                is_current=True,
            )

    def test_end_date_must_follow_start_date(self, db):
        with pytest.raises(IntegrityError), transaction.atomic():
            AcademicYear.objects.create(
                label="2030-31", start_date=date(2031, 6, 1), end_date=date(2030, 6, 1)
            )

    def test_current_raises_a_specific_error_when_none_is_marked(self, year):
        AcademicYear.objects.update(is_current=False)
        with pytest.raises(NoCurrentAcademicYear):
            AcademicYear.objects.current()

    def test_current_returns_the_marked_year(self, year):
        assert AcademicYear.objects.current() == year


class TestOrderImmutability:
    def test_order_number_cannot_change_after_issue(self, faculty, committee, issue_order):
        order = issue_order(faculty=faculty, committee=committee)
        order.order_no = "GPB/TPU/2026-27/999"
        with pytest.raises(RecordImmutable):
            order.save()

    def test_order_date_cannot_change_after_issue(self, faculty, committee, issue_order):
        order = issue_order(faculty=faculty, committee=committee)
        order.order_date = date(2026, 1, 1)
        with pytest.raises(RecordImmutable):
            order.save()

    def test_order_cannot_be_deleted(self, faculty, committee, issue_order):
        order = issue_order(faculty=faculty, committee=committee)
        with pytest.raises(RecordImmutable):
            order.delete()

    def test_assignment_cannot_be_deleted(self, faculty, committee, issue_order):
        order = issue_order(faculty=faculty, committee=committee)
        with pytest.raises(RecordImmutable):
            order.created_assignments.get().delete()

    def test_cancellation_fields_may_still_be_written(self, faculty, committee, issue_order):
        order = issue_order(faculty=faculty, committee=committee)
        order.is_cancelled = True
        order.cancellation_reason = "Issued in error."
        order.save(update_fields=["is_cancelled", "cancellation_reason"])
        order.refresh_from_db()
        assert order.is_cancelled

    def test_a_cancelled_order_must_state_a_reason(self, faculty, committee, issue_order):
        order = issue_order(faculty=faculty, committee=committee)
        order.is_cancelled = True
        with pytest.raises(IntegrityError), transaction.atomic():
            order.save(update_fields=["is_cancelled"])


class TestProtectedReferences:
    def test_committee_with_orders_cannot_be_deleted(self, faculty, committee, issue_order):
        issue_order(faculty=faculty, committee=committee)
        with pytest.raises(ProtectedError):
            committee.delete()

    def test_faculty_with_assignments_cannot_be_deleted(self, faculty, committee, issue_order):
        issue_order(faculty=faculty, committee=committee)
        with pytest.raises(ProtectedError):
            faculty.delete()

    def test_department_in_use_cannot_be_deleted(self, faculty, department):
        with pytest.raises(ProtectedError):
            department.delete()


class TestUserModel:
    def test_email_is_stored_lowercase(self, db):
        user = User.objects.create_user(
            email="Mixed.Case@Test.Local",
            password="x",
            full_name="Test Faculty Four",
            designation=Designation.LECTURER,
            govt_class=GovtClass.CLASS_II,
        )
        assert user.email == "mixed.case@test.local"

    def test_addresses_differing_only_by_case_collide(self, faculty):
        with pytest.raises(IntegrityError), transaction.atomic():
            User.objects.create_user(
                email="Faculty.One@Test.Local",
                password="x",
                full_name="Impostor",
                designation=Designation.LECTURER,
                govt_class=GovtClass.CLASS_II,
            )

    def test_sign_in_lookup_ignores_the_case_typed(self, faculty):
        assert User.objects.get_by_natural_key("FACULTY.ONE@TEST.LOCAL") == faculty

    def test_create_user_requires_an_email(self, db):
        with pytest.raises(ValueError):
            User.objects.create_user(email="", password="x", full_name="Nobody")

    def test_create_superuser_sets_both_flags(self, db):
        admin = User.objects.create_superuser(
            email="root@test.local",
            password="x",
            full_name="Operator",
            designation=Designation.OTHER,
            govt_class=GovtClass.CLASS_I,
        )
        assert admin.is_staff and admin.is_superuser

    def test_is_principal_follows_the_role(self, faculty, principal):
        assert principal.is_principal
        assert not faculty.is_principal

    @pytest.mark.parametrize("number", ["9876543210", "+919876543210", ""])
    def test_valid_mobile_numbers_are_accepted(self, faculty, number):
        faculty.mobile = number
        faculty.full_clean(exclude=["password"])

    @pytest.mark.parametrize("number", ["12345", "98765abcde", "919876543210123"])
    def test_invalid_mobile_numbers_are_rejected(self, faculty, number):
        faculty.mobile = number
        with pytest.raises(ValidationError):
            faculty.full_clean(exclude=["password"])


class TestAuditLog:
    def test_entries_cannot_be_updated(self, faculty):
        entry = AuditLogEntry.objects.create(
            action=AuditAction.LOGIN_SUCCESS, summary="x", object_type="", object_id=""
        )
        entry.summary = "tampered"
        with pytest.raises(RecordImmutable):
            entry.save()

    def test_entries_cannot_be_deleted(self, faculty):
        entry = AuditLogEntry.objects.create(
            action=AuditAction.LOGIN_SUCCESS, summary="x", object_type="", object_id=""
        )
        with pytest.raises(RecordImmutable):
            entry.delete()


class TestManagers:
    @pytest.mark.parametrize(
        "status",
        [
            AssignmentStatus.SUPERSEDED,
            AssignmentStatus.RELINQUISHED,
            AssignmentStatus.EXPIRED,
            AssignmentStatus.CANCELLED,
        ],
    )
    def test_active_excludes_every_other_status(
        self, faculty, committee, issue_order, status
    ):
        order = issue_order(faculty=faculty, committee=committee)
        assignment = order.created_assignments.get()
        Assignment.objects.filter(pk=assignment.pk).update(
            status=status, end_date=date(2026, 8, 1)
        )
        assert Assignment.objects.active().count() == 0

    def test_for_faculty_returns_only_that_person(
        self, faculty, other_faculty, committee, exam_committee, issue_order
    ):
        issue_order(faculty=faculty, committee=committee)
        issue_order(faculty=other_faculty, committee=exam_committee)
        assert Assignment.objects.for_faculty(faculty).count() == 1
        assert Assignment.objects.for_faculty(faculty).get().faculty == faculty

    def test_visible_to_shows_the_principal_everything(
        self, principal, faculty, committee, issue_order
    ):
        issue_order(faculty=faculty, committee=committee)
        from orders.models import Order

        assert Order.objects.visible_to(principal).count() == Order.objects.count()

    def test_visible_to_hides_other_peoples_orders(
        self, faculty, other_faculty, committee, exam_committee, issue_order
    ):
        from orders.models import Order

        mine = issue_order(faculty=faculty, committee=committee)
        issue_order(faculty=other_faculty, committee=exam_committee)
        visible = Order.objects.visible_to(faculty)
        assert list(visible) == [mine]

    def test_visible_to_includes_the_order_that_ended_your_assignment(
        self, faculty, other_faculty, committee, issue_order
    ):
        from orders.models import Order

        issue_order(faculty=faculty, committee=committee)
        superseding = issue_order(
            faculty=other_faculty, committee=committee, order_date=date(2026, 7, 9)
        )
        assert superseding in Order.objects.visible_to(faculty)

    def test_workload_counts_only_active_assignments(
        self, faculty, other_faculty, committee, exam_committee, issue_order
    ):
        issue_order(faculty=faculty, committee=committee)
        issue_order(faculty=faculty, committee=exam_committee, order_date=date(2026, 7, 2))
        issue_order(faculty=other_faculty, committee=committee, order_date=date(2026, 7, 3))
        counts = {u.full_name: u.active_count for u in User.objects.faculty_with_counts()}
        assert counts["Test Faculty One"] == 1  # superseded on TPU, still convener of EXAM
        assert counts["Test Faculty Two"] == 1

    def test_directory_shows_active_rows_without_extra_queries(
        self, faculty, other_faculty, committee, exam_committee, issue_order, django_assert_num_queries
    ):
        issue_order(faculty=faculty, committee=committee)
        issue_order(faculty=other_faculty, committee=exam_committee)
        with django_assert_num_queries(1):
            rows = list(Assignment.objects.directory())
            [(row.faculty.full_name, row.committee.name, row.faculty.department) for row in rows]
        assert len(rows) == 2
