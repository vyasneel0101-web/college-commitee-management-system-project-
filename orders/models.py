from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.crypto import get_random_string
from django.utils.translation import gettext_lazy as _

from core.models import ProtectedRecord, ProtectedRecordQuerySet


def order_file_path(instance, filename):
    """
    orders/{academic_year}/{committee_code}/{order_no_slug}-{random}.docx

    The random component keeps paths non-enumerable even if the storage
    location leaks. docs/03_SECURITY.md §3.
    """
    slug = instance.order_no.replace("/", "-")
    return (
        f"orders/{instance.academic_year.label}/{instance.committee.code}/"
        f"{slug}-{get_random_string(12)}.docx"
    )


class OrderType(models.TextChoices):
    ASSIGNMENT = "ASSIGNMENT", _("Assignment")
    RELINQUISHMENT = "RELINQUISHMENT", _("Relinquishment")
    CORRIGENDUM = "CORRIGENDUM", _("Corrigendum")


class OrderSequence(models.Model):
    """Last issued order number per committee per academic year. Never decremented."""

    academic_year = models.ForeignKey(
        "core.AcademicYear", verbose_name=_("academic year"), on_delete=models.PROTECT
    )
    committee = models.ForeignKey(
        "committees.Committee", verbose_name=_("committee"), on_delete=models.PROTECT
    )
    last_number = models.PositiveIntegerField(_("last number"), default=0)

    class Meta:
        verbose_name = _("order sequence")
        verbose_name_plural = _("order sequences")
        unique_together = [("academic_year", "committee")]

    def __str__(self):
        return f"{self.committee.code} {self.academic_year.label}: {self.last_number}"


class OrderQuerySet(ProtectedRecordQuerySet):
    def visible_to(self, user):
        """
        Every order view and download resolves objects through this.

        Principal: all orders. Faculty: only orders that created or ended one
        of their own assignments. Anyone else: nothing.
        """
        if not getattr(user, "is_authenticated", False) or not user.is_active:
            return self.none()
        if user.is_principal:
            return self.all()
        return self.filter(
            Q(created_assignments__faculty=user) | Q(ended_assignments__faculty=user)
        ).distinct()


class Order(ProtectedRecord):
    """An official, numbered order. Immutable except for the cancellation fields."""

    immutable_fields = (
        "order_no",
        "order_date",
        "academic_year",
        "committee",
        "order_type",
        "issued_by",
        "generated_file",
        "template_used",
        "render_context",
        "remarks",
    )

    order_no = models.CharField(_("order number"), max_length=60, unique=True)
    order_date = models.DateField(_("order date"))
    academic_year = models.ForeignKey(
        "core.AcademicYear", verbose_name=_("academic year"), on_delete=models.PROTECT
    )
    committee = models.ForeignKey(
        "committees.Committee",
        verbose_name=_("committee"),
        on_delete=models.PROTECT,
        related_name="orders",
    )
    order_type = models.CharField(_("order type"), max_length=20, choices=OrderType.choices)
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("issued by"),
        on_delete=models.PROTECT,
        related_name="issued_orders",
    )
    generated_file = models.FileField(
        _("generated file"), upload_to=order_file_path, max_length=255
    )
    # Null for relinquishment and corrigendum orders, which are not rendered
    # from a committee template; always set for assignment orders (BR-7).
    template_used = models.ForeignKey(
        "committees.CommitteeTemplate",
        verbose_name=_("template used"),
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    render_context = models.JSONField(_("render context"))
    remarks = models.TextField(_("remarks"), blank=True)
    is_cancelled = models.BooleanField(_("cancelled"), default=False)
    cancelled_by_order = models.ForeignKey(
        "self",
        verbose_name=_("cancelled by order"),
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="cancels",
    )
    cancellation_reason = models.TextField(_("cancellation reason"), blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    objects = OrderQuerySet.as_manager()

    class Meta:
        ordering = ["-order_date", "-created_at"]
        verbose_name = _("order")
        verbose_name_plural = _("orders")
        indexes = [
            models.Index(fields=["order_date"], name="order_date_idx"),
            models.Index(fields=["academic_year", "committee"], name="order_year_committee_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(is_cancelled=False) | ~Q(cancellation_reason=""),
                name="cancelled_order_has_reason",
            ),
        ]

    def __str__(self):
        return self.order_no
