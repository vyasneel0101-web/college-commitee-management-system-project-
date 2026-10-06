from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.exceptions import RecordImmutable


class AuditAction:
    ORDER_ISSUED = "ORDER_ISSUED"
    ORDER_DOWNLOADED = "ORDER_DOWNLOADED"
    ORDER_CANCELLED = "ORDER_CANCELLED"
    ASSIGNMENT_RELINQUISHED = "ASSIGNMENT_RELINQUISHED"
    ASSIGNMENT_CANCELLED = "ASSIGNMENT_CANCELLED"
    ASSIGNMENT_RESTORED = "ASSIGNMENT_RESTORED"
    ASSIGNMENT_CREATED = "ASSIGNMENT_CREATED"
    ASSIGNMENT_SUPERSEDED = "ASSIGNMENT_SUPERSEDED"
    ASSIGNMENT_EXPIRED = "ASSIGNMENT_EXPIRED"
    TEMPLATE_UPLOADED = "TEMPLATE_UPLOADED"
    LOGIN_SUCCESS = "LOGIN_SUCCESS"
    LOGIN_FAILED = "LOGIN_FAILED"
    PROFILE_UPDATED = "PROFILE_UPDATED"


class AuditLogEntry(models.Model):
    """Append-only. Saving an existing entry or deleting any entry raises."""

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("actor"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_entries",
    )
    action = models.CharField(_("action"), max_length=60, db_index=True)
    object_type = models.CharField(_("object type"), max_length=60)
    object_id = models.CharField(_("object id"), max_length=40)
    summary = models.CharField(_("summary"), max_length=255)
    detail = models.JSONField(_("detail"), default=dict, blank=True)
    ip_address = models.GenericIPAddressField(_("IP address"), null=True, blank=True)
    user_agent = models.CharField(_("user agent"), max_length=300, blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("audit log entry")
        verbose_name_plural = _("audit log entries")
        indexes = [
            models.Index(fields=["actor", "created_at"], name="audit_actor_created_idx"),
        ]

    def __str__(self):
        return self.summary

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise RecordImmutable(_("Audit log entries cannot be changed."))
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RecordImmutable(_("Audit log entries cannot be deleted."))
