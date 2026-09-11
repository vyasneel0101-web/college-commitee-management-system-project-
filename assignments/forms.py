from django import forms
from django.utils.translation import gettext_lazy as _


class DirectoryFilterForm(forms.Form):
    q = forms.CharField(
        label=_("Filter by committee, faculty or department"),
        max_length=100,
        required=False,
    )
