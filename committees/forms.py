from django import forms
from django.utils.translation import gettext_lazy as _

from .models import Committee


class CommitteeForm(forms.ModelForm):
    """Explicit field list. `code` becomes read-only once orders reference it."""

    class Meta:
        model = Committee
        fields = ["name", "code", "description", "allows_multiple_members", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "field"}),
            "code": forms.TextInput(attrs={"class": "field"}),
            "description": forms.Textarea(attrs={"class": "field", "rows": 3}),
        }

    def clean_code(self):
        # The model stores codes uppercase; typing one in lower case is not an error.
        return (self.cleaned_data.get("code") or "").strip().upper()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.code_locked = False
        if self.instance.pk and self.instance.orders.exists():
            # The code is embedded in every order number already issued.
            self.code_locked = True
            self.fields["code"].disabled = True
            self.fields["code"].help_text = _(
                "Fixed: this code appears in order numbers that have already been issued."
            )


class CommitteeTemplateForm(forms.Form):
    docx_file = forms.FileField(
        label=_("Order template (.docx)"),
        widget=forms.ClearableFileInput(attrs={"class": "field", "accept": ".docx"}),
    )
