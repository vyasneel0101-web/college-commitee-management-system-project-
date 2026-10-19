from django.contrib import admin

from core.admin_mixins import ViewOnlyAdminMixin

from .models import Assignment


@admin.register(Assignment)
class AssignmentAdmin(ViewOnlyAdminMixin, admin.ModelAdmin):
    """Status transitions happen only in assignments/services.py."""

    fields = (
        "faculty",
        "committee",
        "role",
        "academic_year",
        "status",
        "start_date",
        "end_date",
        "issuing_order",
        "ending_order",
        "superseded_by",
        "created_at",
    )
    readonly_fields = fields
    list_display = ("faculty", "committee", "role", "status", "start_date", "end_date", "academic_year")
    list_filter = ("status", "role", "academic_year", "committee")
    list_select_related = ("faculty", "committee", "academic_year")
    search_fields = ("faculty__full_name", "committee__name", "committee__code")
