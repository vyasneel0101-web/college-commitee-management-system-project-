from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods, require_safe

from assignments.models import Assignment

from . import services
from .decorators import principal_required
from .forms import DeactivateFacultyForm, FacultyForm, ProfileForm
from .models import User


@login_required
@require_safe
def workload(request):
    """Every active member of staff with their active committees, busiest first."""
    staff = User.objects.faculty_with_counts().prefetch_related(
        Prefetch(
            "assignments",
            queryset=Assignment.objects.active()
            .select_related("committee")
            .order_by("role", "committee__name"),
            to_attr="held",
        )
    )
    return render(request, "accounts/workload.html", {"staff": list(staff)})


@login_required
@require_http_methods(["GET", "POST"])
def profile(request):
    """Own details. Only the mobile number is editable (docs/03_SECURITY.md §2)."""
    if request.method == "POST":
        form = ProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            services.update_own_mobile(
                user=request.user, mobile=form.cleaned_data["mobile"], request=request
            )
            messages.success(request, _("Mobile number saved."))
            return redirect("accounts:profile")
    else:
        form = ProfileForm(instance=request.user)
    return render(request, "accounts/profile.html", {"form": form})


@principal_required
@require_safe
def faculty_list(request):
    """Every staff record, including deactivated ones, with their committee load."""
    people = User.objects.faculty_with_counts(include_inactive=True)
    return render(request, "accounts/faculty_list.html", {"people": list(people)})


@principal_required
@require_http_methods(["GET", "POST"])
def faculty_create(request):
    form = FacultyForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        person = services.create_faculty(
            created_by=request.user, request=request, **form.cleaned_data
        )
        messages.success(request, _("Faculty record added."))
        return redirect("accounts:faculty_detail", pk=person.pk)
    return render(request, "accounts/faculty_form.html", {"form": form, "person": None})


@principal_required
@require_http_methods(["GET", "POST"])
def faculty_edit(request, pk):
    person = get_object_or_404(User, pk=pk)
    form = FacultyForm(request.POST or None, instance=person)
    if request.method == "POST" and form.is_valid():
        if form.changed_data:
            services.update_faculty(
                user=person,
                actor=request.user,
                changed_fields=form.changed_data,
                request=request,
            )
        messages.success(request, _("Faculty record saved."))
        return redirect("accounts:faculty_detail", pk=person.pk)
    return render(request, "accounts/faculty_form.html", {"form": form, "person": person})


@principal_required
@require_safe
def faculty_detail(request, pk):
    person = get_object_or_404(User.objects.select_related("department"), pk=pk)
    assignments = (
        Assignment.objects.for_faculty(person)
        .select_related("committee", "issuing_order")
        .order_by("status", "-start_date")
    )
    return render(
        request,
        "accounts/faculty_detail.html",
        {"person": person, "assignments": list(assignments)},
    )


@principal_required
@require_http_methods(["GET", "POST"])
def faculty_deactivate(request, pk):
    """Deactivation stops sign-in only; active assignments must still be relinquished (BR-9)."""
    person = get_object_or_404(User.objects.filter(is_active=True), pk=pk)
    active = list(
        Assignment.objects.active().select_related("committee").filter(faculty=person)
    )
    form = DeactivateFacultyForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        services.deactivate_faculty(user=person, actor=request.user, request=request)
        messages.success(request, _("Faculty deactivated."))
        return redirect("accounts:faculty_detail", pk=person.pk)
    return render(
        request,
        "accounts/faculty_deactivate.html",
        {"person": person, "form": form, "active": active},
    )
