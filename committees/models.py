from django.conf import settings
from django.core.validators import FileExtensionValidator, RegexValidator
from django.db import models
from django.db.models import Q
from django.db.models.functions import Upper
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.utils.translation import gettext_lazy as _

from core.exceptions import RecordImmutable


def committee_template_path(instance, filename):
    """Never use the uploaded filename on disk. docs/03_SECURITY.md §5."""
    return (
        f"templates/{timezone.now():%Y}/"
        f"{instance.committee.code}-v{instance.version}-{get_random_string(12)}.docx"
    )


class Committee(models.Model):
    name = models.CharField(_("name"), max_length=200, unique=True)
    code = models.CharField(
        _("code"),
        max_length=15,
        unique=True,
        validators=[
            RegexValidator(
                r"^[A-Z0-9]+$", _("Use capital letters and digits only, for example TPU.")
            )
        ],
    )
    description = models.TextField(_("description"), blank=True)
    allows_multiple_members = models.BooleanField(
        _("allows multiple members"),
        default=True,
        help_text=_("If unticked, only a convener may be assigned."),
    )
    is_active = models.BooleanField(_("active"), default=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = _("committee")
        verbose_name_plural = _("committees")
        constraints = [
            models.CheckConstraint(
                condition=Q(code=Upper("code")), name="committee_code_uppercase"
            ),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        self.code = self.code.strip().upper()
        if not self._state.adding:
            stored_code = (
                Committee.objects.filter(pk=self.pk).values_list("code", flat=True).first()
            )
            if stored_code is not None and stored_code != self.code and self.orders.exists():
                raise RecordImmutable(
                    _(
                        "The committee code cannot change once an order has been issued, "
                        "because it is part of every order number."
                    )
                )
        super().save(*args, **kwargs)


class CommitteeTemplate(models.Model):
    """A versioned Word order template. Old versions are kept: they document past orders."""

    committee = models.ForeignKey(
        Committee,
        verbose_name=_("committee"),
        on_delete=models.PROTECT,
        related_name="templates",
    )
    version = models.PositiveIntegerField(_("version"))
    docx_file = models.FileField(
        _("Word file"),
        upload_to=committee_template_path,
        max_length=255,
        validators=[FileExtensionValidator(allowed_extensions=["docx"])],
    )
    is_active = models.BooleanField(_("active"), default=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("uploaded by"),
        on_delete=models.PROTECT,
        related_name="uploaded_templates",
    )
    uploaded_at = models.DateTimeField(_("uploaded at"), auto_now_add=True)
    detected_placeholders = models.JSONField(
        _("detected placeholders"), default=list, blank=True
    )

    class Meta:
        ordering = ["committee_id", "-version"]
        verbose_name = _("committee template")
        verbose_name_plural = _("committee templates")
        unique_together = [("committee", "version")]
        constraints = [
            models.UniqueConstraint(
                fields=["committee"],
                condition=Q(is_active=True),
                name="uniq_active_committee_template",
            ),
        ]

    def __str__(self):
        return f"{self.committee.code} v{self.version}"
