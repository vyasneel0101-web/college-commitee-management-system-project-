from django import forms
from django.forms import formset_factory
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.utils.translation import ngettext

from accounts.models import ExternalMember, User
from assignments.models import AssignmentRole
from committees.models import Committee

STAFF = "u"
EXTERNAL = "x"


def holder_choices():
    """
    Everyone who can be appointed, in two groups: staff with accounts, and
    people from outside the college (docs/11_REAL_ORDERS.md §3).

    Each staff entry shows the department and how many committees that person
    already holds, so an overloaded person is visible before being chosen.
    """
    staff = []
    for person in User.objects.faculty_with_counts():
        department = person.department.code if person.department else "—"
        count = ngettext(
            "%(count)d active committee", "%(count)d active committees", person.active_count
        ) % {"count": person.active_count}
        staff.append((f"{STAFF}:{person.pk}", f"{person.full_name} · {department} · {count}"))

    external = [
        (f"{EXTERNAL}:{member.pk}", f"{member.full_name} · {member.organisation}")
        for member in ExternalMember.objects.filter(is_active=True)
    ]

    choices = [("", _("Choose a person"))]
    if staff:
        choices.append((_("Staff"), staff))
    if external:
        choices.append((_("From outside the college"), external))
    return choices


def resolve_holder(value):
    """Turn a "u:3" or "x:1" choice back into the person it names."""
    kind, _sep, pk = (value or "").partition(":")
    if kind == STAFF:
        return User.objects.filter(pk=pk).first()
    if kind == EXTERNAL:
        return ExternalMember.objects.filter(pk=pk).first()
    return None


class AppointmentForm(forms.Form):
    """One line of the order's table: who, and in what role."""

    person = forms.ChoiceField(label=_("Person"), required=False)
    role = forms.ChoiceField(label=_("Role"), required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["person"].choices = holder_choices()
        self.fields["role"].choices = [("", _("Choose a role"))] + AssignmentRole.choices
        for name in ("person", "role"):
            self.fields[name].widget.attrs["class"] = "field"

    def clean(self):
        cleaned = super().clean()
        person, role = cleaned.get("person"), cleaned.get("role")
        if not person and not role:
            return cleaned  # an untouched row, ignored
        if not person:
            self.add_error("person", _("Choose a person, or clear the role."))
        if not role:
            self.add_error("role", _("Choose a role for this person."))
        if person and role:
            holder = resolve_holder(person)
            if holder is None:
                self.add_error("person", _("That person is no longer on the list."))
            else:
                cleaned["holder"] = holder
        return cleaned


class BaseAppointmentFormSet(forms.BaseFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        if not self.appointments():
            raise forms.ValidationError(_("Name at least one person on the order."))

    def appointments(self):
        """The filled-in rows, as (holder, role) pairs."""
        return [
            (form.cleaned_data["holder"], form.cleaned_data["role"])
            for form in self.forms
            if form.cleaned_data.get("holder")
        ]


AppointmentFormSet = formset_factory(
    AppointmentForm, formset=BaseAppointmentFormSet, extra=3, max_num=20
)


class AssignCommitteeForm(forms.Form):
    committee = forms.ModelChoiceField(
        label=_("Committee"),
        queryset=Committee.objects.filter(is_active=True),
        empty_label=_("Choose a committee"),
    )
    order_date = forms.DateField(
        label=_("Order date"),
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )
    references = forms.CharField(
        label=_("References"),
        required=False,
        max_length=500,
        widget=forms.Textarea(attrs={"rows": 2}),
    )
    remarks = forms.CharField(
        label=_("Remarks"),
        required=False,
        max_length=500,
        widget=forms.Textarea(attrs={"rows": 2}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in self.fields:
            self.fields[name].widget.attrs["class"] = "field"
        self.fields["order_date"].widget.attrs["max"] = timezone.localdate().isoformat()


class CancelOrderForm(forms.Form):
    reason = forms.CharField(
        label=_("Reason for cancelling"),
        min_length=10,
        max_length=500,
        widget=forms.Textarea(attrs={"rows": 3, "class": "field"}),
        error_messages={
            "required": _("State why the order is being cancelled. It is printed on the corrigendum."),
            "min_length": _("Give a fuller reason: it is printed on the corrigendum."),
        },
    )


class RelinquishForm(forms.Form):
    order_date = forms.DateField(
        label=_("Order date"),
        widget=forms.DateInput(attrs={"type": "date", "class": "field"}, format="%Y-%m-%d"),
    )
    remarks = forms.CharField(
        label=_("Remarks"),
        required=False,
        max_length=500,
        widget=forms.Textarea(attrs={"rows": 3, "class": "field"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["order_date"].widget.attrs["max"] = timezone.localdate().isoformat()
