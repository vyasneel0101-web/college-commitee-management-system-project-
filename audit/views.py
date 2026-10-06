from django import forms
from django.core.paginator import Paginator
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_safe

from accounts.decorators import principal_required

from .models import ACTION_LABELS, AuditLogEntry

PAGE_SIZE = 50


class AuditFilterForm(forms.Form):
    action = forms.ChoiceField(
        label=_("Action"),
        required=False,
        choices=[("", _("All actions"))] + [(value, label) for value, label in ACTION_LABELS.items()],
    )


@principal_required
@require_safe
def log(request):
    """
    The audit trail, newest first. Read-only: there is no view anywhere that
    edits or deletes an entry, and the model refuses both.
    """
    form = AuditFilterForm(request.GET)
    entries = AuditLogEntry.objects.select_related("actor")
    action = form.cleaned_data["action"] if form.is_valid() else ""
    if action:
        entries = entries.filter(action=action)
    page = Paginator(entries, PAGE_SIZE).get_page(request.GET.get("page"))
    return render(request, "audit/log.html", {"form": form, "page": page, "action": action})
