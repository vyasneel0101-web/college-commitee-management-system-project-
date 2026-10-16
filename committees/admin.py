from django.contrib import admin

from .models import Committee


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
