from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class NotificationQuerySet(models.QuerySet):
    def unread(self):
        return self.filter(read_at__isnull=True)


class Notification(models.Model):
    """
    An in-app message to one member of staff about a change to a committee
    they are on, or were on until that change.

    Created inside the same transaction as the order that caused it, so a
    failed order never leaves a stray notification.
    """

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("recipient"),
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    committee = models.ForeignKey(
        "committees.Committee",
        verbose_name=_("committee"),
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    order = models.ForeignKey(
        "orders.Order",
        verbose_name=_("order"),
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    message = models.CharField(_("message"), max_length=500)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    read_at = models.DateTimeField(_("read at"), null=True, blank=True)

    objects = NotificationQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = _("notification")
        verbose_name_plural = _("notifications")
        indexes = [models.Index(fields=["recipient", "read_at"], name="notification_unread_idx")]

    def __str__(self):
        return f"{self.recipient}: {self.message[:60]}"

    @property
    def is_unread(self):
        return self.read_at is None
