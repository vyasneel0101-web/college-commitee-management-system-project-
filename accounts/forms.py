from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.utils.translation import gettext_lazy as _

from .models import User


class EmailAuthenticationForm(AuthenticationForm):
    error_messages = {
        "invalid_login": _(
            "The email address or password is not correct. Check both and try again."
        ),
        "inactive": _("This account is inactive. Contact the Principal’s office."),
    }


class ProfileForm(forms.ModelForm):
    """
    The only field a user may change on their own record. `role`,
    `is_active` and every official detail are deliberately absent.
    """

    class Meta:
        model = User
        fields = ["mobile"]


class FacultyForm(forms.ModelForm):
    """
    Used by the Principal to create and correct staff records.

    `role`, `is_active`, `is_staff`, `is_superuser` and `signature_image` are
    deliberately absent: a role is never settable through a web form
    (docs/03_SECURITY.md §2).
    """

    class Meta:
        model = User
        fields = [
            "salutation",
            "full_name",
            "email",
            "designation",
            "govt_class",
            "department",
            "employee_code",
            "joining_date",
            "mobile",
        ]
        widgets = {
            "salutation": forms.TextInput(attrs={"class": "field"}),
            "full_name": forms.TextInput(attrs={"class": "field"}),
            "email": forms.EmailInput(attrs={"class": "field"}),
            "employee_code": forms.TextInput(attrs={"class": "field"}),
            "joining_date": forms.DateInput(attrs={"class": "field", "type": "date"}, format="%Y-%m-%d"),
            "mobile": forms.TextInput(attrs={"class": "field", "type": "tel"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("designation", "govt_class", "department"):
            self.fields[name].widget.attrs["class"] = "field"


class DeactivateFacultyForm(forms.Form):
    confirm = forms.BooleanField(
        label=_("I understand this person will no longer be able to sign in"),
        error_messages={"required": _("Tick the box to confirm.")},
    )
