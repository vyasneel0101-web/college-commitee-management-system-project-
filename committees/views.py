from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods, require_safe

from accounts.decorators import principal_required
from assignments.models import Assignment, AssignmentRole
from orders.forms import AppointmentFormSet

from . import services
from .forms import CommitteeForm
from .models import Committee


@login_required
@require_safe
def committee_list(request):
    """Every committee with who holds it. Read-only for faculty."""
    committees = (
        Committee.objects.annotate(
            active_count=Count("assignments", filter=Q(assignments__status="ACTIVE"))
        )
        .prefetch_related(
            Prefetch(
                "assignments",
                queryset=Assignment.objects.active()
                .select_related("faculty")
                .order_by("role", "faculty__full_name"),
                to_attr="held_by",
            ),
        )
        .order_by("name")
    )
    return render(request, "committees/list.html", {"committees": list(committees)})


@principal_required
@require_http_methods(["GET", "POST"])
def committee_create(request):
    form = CommitteeForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        committee = form.save()
        messages.success(request, _("Committee added."))
        return redirect("committees:detail", pk=committee.pk)
    return render(request, "committees/form.html", {"form": form, "committee": None})


@principal_required
@require_http_methods(["GET", "POST"])
def committee_edit(request, pk):
    committee = get_object_or_404(Committee, pk=pk)
    form = CommitteeForm(request.POST or None, instance=committee)
    if request.method == "POST" and form.is_valid():
        if form.changed_data:
            services.update_committee(form=form, actor=request.user, request=request)
            messages.success(request, _("Committee saved. Everyone on it has been notified."))
        else:
            messages.success(request, _("Nothing changed."))
        return redirect("committees:edit", pk=committee.pk)
    context = {
        "form": form,
        "committee": committee,
        # Members are managed here: removing one issues a relinquishment
        # order, adding one goes through the usual preview and order.
        "held_by": list(
            Assignment.objects.active()
            .select_related("faculty", "faculty__department", "external_member")
            .filter(committee=committee)
            .order_by("role", "faculty__full_name", "external_member__full_name")
        ),
        "add_formset": AppointmentFormSet(),
        "today": timezone.localdate(),
    }
    return render(request, "committees/form.html", context)


@login_required
@require_safe
def committee_detail(request, pk):
    committee = get_object_or_404(Committee, pk=pk)
    context = {
        "committee": committee,
        "held_by": list(
            Assignment.objects.active()
            .select_related("faculty", "faculty__department")
            .filter(committee=committee)
            .order_by("role", "faculty__full_name")
        ),
        "order_count": committee.orders.count(),
    }
    return render(request, "committees/detail.html", context)
