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
