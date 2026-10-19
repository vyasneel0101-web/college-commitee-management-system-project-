from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import AdminUserCreationForm, UserChangeForm
from django.utils.translation import gettext_lazy as _

from .models import Department, User

ACCESS_FIELDS = ("role", "is_active", "is_staff", "is_superuser", "groups", "user_permissions")


class StaffCreationForm(AdminUserCreationForm):
    class Meta:
        model = User
        fields = ("email", "salutation", "full_name", "designation", "govt_class", "department")


class StaffChangeForm(UserChangeForm):
    class Meta:
        model = User
        fields = (
            "email",
            "salutation",
            "full_name",
            "designation",
            "govt_class",
            "department",
            "employee_code",
            "joining_date",
            "mobile",
            "signature_image",
            *ACCESS_FIELDS,
        )


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    fields = ("name", "code", "is_active")
    list_display = ("name", "code", "is_active")
    search_fields = ("name", "code")


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    """
    `role` is editable only by a superuser (CLAUDE.md security rule 5). Users
    are deactivated, never deleted.
    """

    form = StaffChangeForm
    add_form = StaffCreationForm
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (
            _("Official details"),
            {
                "fields": (
                    "salutation",
                    "full_name",
                    "designation",
                    "govt_class",
                    "department",
                    "employee_code",
                    "joining_date",
                )
            },
        ),
        (_("Contact"), {"fields": ("mobile",)}),
        (_("Signature"), {"fields": ("signature_image",)}),
        (_("Access"), {"fields": ACCESS_FIELDS}),
        (_("Record"), {"fields": ("created_by", "last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "salutation",
                    "full_name",
                    "designation",
                    "govt_class",
                    "department",
                    "usable_password",
                    "password1",
                    "password2",
                ),
            },
        ),
    )
    readonly_fields = ("created_by", "last_login", "date_joined")
    list_display = ("full_name", "email", "role", "designation", "department", "is_active")
    list_filter = ("role", "designation", "department", "is_active")
    list_select_related = ("department",)
    search_fields = ("full_name", "email", "employee_code")
    ordering = ("full_name",)
    filter_horizontal = ("groups", "user_permissions")

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if not request.user.is_superuser:
            readonly += ["role", "is_staff", "is_superuser", "groups", "user_permissions"]
        return readonly

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
