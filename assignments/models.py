from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.utils.translation import gettext_lazy as _

from core.models import ProtectedRecord, ProtectedRecordQuerySet


class AssignmentRole(models.TextChoices):
    CONVENER = "CONVENER", _("Convener")
    MEMBER = "MEMBER", _("Member")


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
            .select_related("faculty", "committee", "faculty__department")
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
        "committee",
        "role",
        "academic_year",
        "start_date",
        "issuing_order",
    )

    faculty = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("faculty"),
        on_delete=models.PROTECT,
        related_name="assignments",
    )
    committee = models.ForeignKey(
        "committees.Committee",
        verbose_name=_("committee"),
        on_delete=models.PROTECT,
        related_name="assignments",
    )
    role = models.CharField(_("role"), max_length=20, choices=AssignmentRole.choices)
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
                fields=["committee"],
                condition=Q(status="ACTIVE", role="CONVENER"),
                name="uniq_active_convener",
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
        return f"{self.faculty} — {self.get_role_display()}, {self.committee.code}"
