from django.contrib import admin

from .models import AcademicYear


@admin.register(AcademicYear)
class AcademicYearAdmin(admin.ModelAdmin):
    fields = ("label", "start_date", "end_date", "is_current")
    list_display = ("label", "start_date", "end_date", "is_current")

    def has_delete_permission(self, request, obj=None):
        return False
