from django.contrib import admin

from core.admin_mixins import ViewOnlyAdminMixin

from .models import AuditLogEntry


@admin.register(AuditLogEntry)
class AuditLogEntryAdmin(ViewOnlyAdminMixin, admin.ModelAdmin):
    fields = (
        "created_at",
        "actor",
        "action",
        "object_type",
        "object_id",
        "summary",
        "detail",
        "ip_address",
        "user_agent",
    )
    readonly_fields = fields
    list_display = ("created_at", "actor", "action", "summary")
    list_filter = ("action",)
    list_select_related = ("actor",)
    search_fields = ("summary", "object_id")
