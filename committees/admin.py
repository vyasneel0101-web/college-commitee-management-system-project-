from django.contrib import admin

from core.admin_mixins import ViewOnlyAdminMixin

from .models import Committee, CommitteeTemplate


@admin.register(Committee)
class CommitteeAdmin(admin.ModelAdmin):
    fields = ("name", "code", "description", "allows_multiple_members", "is_active")
    list_display = ("name", "code", "allows_multiple_members", "is_active")
    list_filter = ("is_active", "allows_multiple_members")
    search_fields = ("name", "code")

    def get_readonly_fields(self, request, obj=None):
        # The code is embedded in order numbers once an order exists.
        if obj is not None and obj.orders.exists():
            return ("code",)
        return ()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CommitteeTemplate)
class CommitteeTemplateAdmin(ViewOnlyAdminMixin, admin.ModelAdmin):
    """Uploads go through committees.services.upload_committee_template (validation chain)."""

    fields = (
        "committee",
        "version",
        "docx_file",
        "is_active",
        "uploaded_by",
        "uploaded_at",
        "detected_placeholders",
    )
    readonly_fields = fields
    list_display = ("committee", "version", "is_active", "uploaded_by", "uploaded_at")
    list_filter = ("is_active", "committee")
    list_select_related = ("committee", "uploaded_by")
