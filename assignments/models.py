from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.utils.translation import gettext_lazy as _

from core.models import ProtectedRecord, ProtectedRecordQuerySet


class AssignmentRole(models.TextChoices):
    """
    The complete role list, taken from the college's real orders
    (docs/11_REAL_ORDERS.md §2). "Convener" was a guess and is not used here.
    """

    PRESIDING_OFFICER = "PRESIDING_OFFICER", _("Presiding Officer")
    NODAL_OFFICER = "NODAL_OFFICER", _("Nodal Officer")
    MEMBER = "MEMBER", _("Member")
    EXTERNAL_MEMBER = "EXTERNAL_MEMBER", _("External Member")


# A committee has at most one person in charge: a Presiding Officer or a Nodal
# Officer, never both. Members are unlimited.
LEAD_ROLES = (AssignmentRole.PRESIDING_OFFICER, AssignmentRole.NODAL_OFFICER)


class AssignmentStatus(models.TextChoices):
    ACTIVE = "ACTIVE", _("Active")
    SUPERSEDED = "SUPERSEDED", _("Superseded")
    RELINQUISHED = "RELINQUISHED", _("Relinquished")
    EXPIRED = "EXPIRED", _("Expired")
    CANCELLED = "CANCELLED", _("Cancelled")


class AssignmentQuerySet(ProtectedRecordQuerySet):
    def active(self):
        return self.filter(status=AssignmentStatus.ACTIVE)

    def for_faculty(self, user):
        return self.filter(faculty=user)

    def directory(self):
        return (
            self.active()
            .select_related(
                "faculty", "committee", "faculty__department", "external_member"
            )
            .order_by("committee__name", "role", "faculty__full_name")
        )

    def matching(self, text):
        """Filter by committee name or code, faculty name, or department name or code."""
        if not text:
            return self
        return self.filter(
            Q(committee__name__icontains=text)
            | Q(committee__code__iexact=text)
            | Q(faculty__full_name__icontains=text)
            | Q(external_member__full_name__icontains=text)
            | Q(faculty__department__name__icontains=text)
            | Q(faculty__department__code__iexact=text)
        )


class Assignment(ProtectedRecord):
    """
    A faculty member's role in a committee, created by an order.

    Never deleted. After creation only the status transition fields change
    (status, end_date, ending_order, superseded_by), and only through
    assignments/services.py.
    """

    immutable_fields = (
        "faculty",
        "external_member",
        "committee",
        "role",
        "academic_year",
        "start_date",
        "issuing_order",
    )

    # Exactly one of these two holds the role: a member of staff with an
    # account, or somebody from outside the college who has none.
    faculty = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("staff member"),
        on_delete=models.PROTECT,
        related_name="assignments",
        null=True,
        blank=True,
    )
    external_member = models.ForeignKey(
        "accounts.ExternalMember",
        verbose_name=_("external member"),
        on_delete=models.PROTECT,
        related_name="assignments",
        null=True,
        blank=True,
    )
    committee = models.ForeignKey(
        "committees.Committee",
        verbose_name=_("committee"),
        on_delete=models.PROTECT,
        related_name="assignments",
    )
    role = models.CharField(_("role"), max_length=30, choices=AssignmentRole.choices)
    academic_year = models.ForeignKey(
        "core.AcademicYear", verbose_name=_("academic year"), on_delete=models.PROTECT
    )
    status = models.CharField(
        _("status"), max_length=20, choices=AssignmentStatus.choices, db_index=True
    )
    start_date = models.DateField(_("start date"))
    end_date = models.DateField(_("end date"), null=True, blank=True)
    issuing_order = models.ForeignKey(
        "orders.Order",
        verbose_name=_("issuing order"),
        on_delete=models.PROTECT,
        related_name="created_assignments",
    )
    ending_order = models.ForeignKey(
        "orders.Order",
        verbose_name=_("ending order"),
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="ended_assignments",
    )
    superseded_by = models.ForeignKey(
        "self",
        verbose_name=_("superseded by"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="supersedes",
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    objects = AssignmentQuerySet.as_manager()

    class Meta:
        ordering = ["-start_date", "-created_at"]
        verbose_name = _("assignment")
        verbose_name_plural = _("assignments")
        indexes = [
            models.Index(fields=["status", "committee"], name="assignment_status_cttee_idx"),
            models.Index(fields=["faculty", "status"], name="assignment_faculty_status_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["faculty", "committee", "role"],
                condition=Q(status="ACTIVE"),
                name="uniq_active_assignment",
            ),
            models.UniqueConstraint(
                fields=["external_member", "committee", "role"],
                condition=Q(status="ACTIVE"),
                name="uniq_active_external_assignment",
            ),
            # One person in charge per committee: Presiding Officer or Nodal
            # Officer, never both (docs/11_REAL_ORDERS.md §2).
            models.UniqueConstraint(
                fields=["committee"],
                condition=Q(status="ACTIVE", role__in=["PRESIDING_OFFICER", "NODAL_OFFICER"]),
                name="uniq_active_lead",
            ),
            models.CheckConstraint(
                condition=Q(faculty__isnull=False, external_member__isnull=True)
                | Q(faculty__isnull=True, external_member__isnull=False),
                name="assignment_has_exactly_one_holder",
            ),
            models.CheckConstraint(
                condition=Q(external_member__isnull=True) | Q(role="EXTERNAL_MEMBER"),
                name="external_member_holds_external_role",
            ),
            models.CheckConstraint(
                condition=Q(status="ACTIVE", end_date__isnull=True) | ~Q(status="ACTIVE"),
                name="active_has_no_end_date",
            ),
            models.CheckConstraint(
                condition=Q(status__in=["ACTIVE", "CANCELLED"]) | Q(end_date__isnull=False),
                name="ended_assignment_has_end_date",
            ),
            models.CheckConstraint(
                condition=Q(end_date__isnull=True) | Q(end_date__gte=F("start_date")),
                name="end_date_not_before_start_date",
            ),
        ]

    def __str__(self):
        return f"{self.holder_name} — {self.get_role_display()}, {self.committee.code}"

    @property
    def holder(self):
        """The staff member or the external member — whichever holds this role."""
        return self.faculty or self.external_member

    @property
    def holder_name(self):
        holder = self.holder
        return holder.full_name if holder else ""

    @property
    def holder_detail(self):
        """Designation and department, or the external member's organisation."""
        if self.faculty:
            parts = [self.faculty.get_designation_display()]
            if self.faculty.department:
                parts.append(self.faculty.department.name)
            return ", ".join(part for part in parts if part)
        return self.external_member.organisation if self.external_member else ""
