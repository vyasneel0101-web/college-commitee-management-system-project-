from django.contrib import admin

from core.admin_mixins import ViewOnlyAdminMixin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(ViewOnlyAdminMixin, admin.ModelAdmin):
    fields = ("recipient", "committee", "order", "message", "created_at", "read_at")
    readonly_fields = fields
    list_display = ("recipient", "committee", "message", "created_at", "read_at")
    list_select_related = ("recipient", "committee")
