from django.core.validators import RegexValidator
from django.db import models
from django.db.models import F, Q
from django.utils.text import capfirst
from django.utils.translation import gettext_lazy as _

from .exceptions import NoCurrentAcademicYear, RecordImmutable


class ProtectedRecordQuerySet(models.QuerySet):
    """QuerySet for records that form the official history. Bulk deletion is refused."""

    def delete(self):
        raise RecordImmutable(
            capfirst(
                _("%(records)s are never deleted.")
                % {"records": self.model._meta.verbose_name_plural}
            )
        )


class ProtectedRecord(models.Model):
    """
    Abstract base for Order and Assignment.

    Invariant: an instance is never deleted, and no field named in
    `immutable_fields` changes after the first save. Corrections are made by
    issuing new orders, never by editing old ones.
    """

    immutable_fields: tuple[str, ...] = ()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self._state.adding and self.immutable_fields:
            self._refuse_changes_to_immutable_fields()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RecordImmutable(
            capfirst(
                _("%(record)s records are never deleted.")
                % {"record": self._meta.verbose_name}
            )
        )

    def _refuse_changes_to_immutable_fields(self):
        attnames = [self._meta.get_field(name).attname for name in self.immutable_fields]
        stored = type(self)._base_manager.filter(pk=self.pk).values(*attnames).first()
        if stored is None:
            return
        changed = [name for name in attnames if getattr(self, name) != stored[name]]
        if changed:
            raise RecordImmutable(
                capfirst(
                    _("%(record)s fields cannot be changed after creation: %(fields)s.")
                    % {"record": self._meta.verbose_name, "fields": ", ".join(changed)}
                )
            )


class AcademicYearQuerySet(models.QuerySet):
    def current(self):
        try:
            return self.get(is_current=True)
        except self.model.DoesNotExist as exc:
            raise NoCurrentAcademicYear() from exc


class AcademicYear(models.Model):
    label = models.CharField(
        _("label"),
        max_length=9,
        unique=True,
        validators=[
            RegexValidator(
                r"^\d{4}-\d{2}$", _("Use the format YYYY-YY, for example 2026-27.")
            )
        ],
    )
    start_date = models.DateField(_("start date"))
    end_date = models.DateField(_("end date"))
    is_current = models.BooleanField(_("current"), default=False)

    objects = AcademicYearQuerySet.as_manager()

    class Meta:
        ordering = ["-start_date"]
        verbose_name = _("academic year")
        verbose_name_plural = _("academic years")
        constraints = [
            models.CheckConstraint(
                condition=Q(end_date__gt=F("start_date")),
                name="academic_year_ends_after_start",
            ),
            models.UniqueConstraint(
                fields=["is_current"],
                condition=Q(is_current=True),
                name="uniq_current_academic_year",
            ),
        ]

    def __str__(self):
        return self.label

    def contains(self, day):
        return self.start_date <= day <= self.end_date
