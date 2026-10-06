from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods, require_safe

from accounts.decorators import principal_required
from assignments.models import Assignment
from core.exceptions import DomainError

from . import services
from .forms import CommitteeForm, CommitteeTemplateForm
from .models import Committee, CommitteeTemplate


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
            Prefetch(
                "templates",
                queryset=CommitteeTemplate.objects.filter(is_active=True),
                to_attr="active_template",
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
        form.save()
        messages.success(request, _("Committee saved."))
        return redirect("committees:detail", pk=committee.pk)
    return render(request, "committees/form.html", {"form": form, "committee": committee})


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
        "templates": list(committee.templates.select_related("uploaded_by").order_by("-version")),
        "order_count": committee.orders.count(),
    }
    return render(request, "committees/detail.html", context)


@principal_required
@require_http_methods(["GET", "POST"])
def committee_template_upload(request, pk):
    """Upload a new template version. The old version is kept: past orders came from it."""
    committee = get_object_or_404(Committee, pk=pk)
    form = CommitteeTemplateForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        try:
            template = services.upload_committee_template(
                committee=committee,
                uploaded_file=form.cleaned_data["docx_file"],
                uploaded_by=request.user,
            )
        except DomainError as exc:
            form.add_error("docx_file", exc.message)
        else:
            messages.success(
                request,
                _("Template version %(version)s uploaded.") % {"version": template.version},
            )
            return redirect("committees:detail", pk=committee.pk)
    return render(
        request,
        "committees/template_upload.html",
        {"form": form, "committee": committee, "required": services.REQUIRED_PLACEHOLDERS},
    )
