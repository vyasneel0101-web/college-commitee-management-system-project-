from django.contrib import admin

from core.admin_mixins import ViewOnlyAdminMixin

from .models import Order, OrderSequence


@admin.register(Order)
class OrderAdmin(ViewOnlyAdminMixin, admin.ModelAdmin):
    """Orders are immutable. Files are downloaded through the permission-checked view, not here."""

    fields = (
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
        "is_cancelled",
        "cancelled_by_order",
        "cancellation_reason",
        "created_at",
    )
    readonly_fields = fields
    list_display = ("order_no", "order_date", "committee", "order_type", "issued_by", "is_cancelled")
    list_filter = ("academic_year", "order_type", "is_cancelled", "committee")
    list_select_related = ("committee", "issued_by")
    search_fields = ("order_no",)
    date_hierarchy = "order_date"


@admin.register(OrderSequence)
class OrderSequenceAdmin(ViewOnlyAdminMixin, admin.ModelAdmin):
    fields = ("academic_year", "committee", "last_number")
    readonly_fields = fields
    list_display = ("committee", "academic_year", "last_number")
    list_select_related = ("committee", "academic_year")
