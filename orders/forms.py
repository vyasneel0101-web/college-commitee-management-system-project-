from django import forms
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.utils.translation import ngettext

from accounts.models import User
from assignments.models import AssignmentRole
from committees.models import Committee


class FacultyChoiceField(forms.ModelChoiceField):
    """Shows the current committee count so an overloaded person is visible before choosing."""

    def label_from_instance(self, person):
        department = person.department.code if person.department else "—"
        count = ngettext(
            "%(count)d active committee", "%(count)d active committees", person.active_count
        ) % {"count": person.active_count}
        return f"{person.full_name} · {department} · {count}"


class AssignCommitteeForm(forms.Form):
    committee = forms.ModelChoiceField(
        label=_("Committee"),
        queryset=Committee.objects.filter(is_active=True),
        empty_label=_("Choose a committee"),
    )
    faculty = FacultyChoiceField(
        label=_("Faculty member"), queryset=User.objects.none(), empty_label=None
    )
    role = forms.ChoiceField(
        label=_("Role"), choices=AssignmentRole.choices, widget=forms.RadioSelect
    )
    order_date = forms.DateField(
        label=_("Order date"),
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )
    remarks = forms.CharField(
        label=_("Remarks"),
        required=False,
        max_length=500,
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["faculty"].queryset = User.objects.faculty_with_counts()
        for name in ("committee", "faculty", "order_date", "remarks"):
            self.fields[name].widget.attrs["class"] = "field"
        self.fields["faculty"].widget.attrs["size"] = 8
        self.fields["order_date"].widget.attrs["max"] = timezone.localdate().isoformat()
