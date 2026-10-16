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
    """Kept only because migration 0001 refers to it. Templates are now global."""
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
