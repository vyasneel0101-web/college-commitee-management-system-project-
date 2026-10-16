from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_http_methods, require_safe

from accounts.decorators import principal_required
from audit import services as audit
from audit.models import AuditAction
from core.exceptions import DomainError, PreviewOutdated

from . import services
from assignments.models import Assignment, AssignmentRole, AssignmentStatus

from .forms import (
    AppointmentFormSet,
    AssignCommitteeForm,
    CancelOrderForm,
    RelinquishForm,
)
from .models import Order

DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _describe(holder):
    """Designation and department, or an external member's organisation."""
    organisation = getattr(holder, "organisation", None)
    if organisation:
        return organisation
    parts = [holder.get_designation_display()]
    if holder.department:
        parts.append(holder.department.name)
    return ", ".join(part for part in parts if part)


def _expected_superseded_id(post):
    """The holder the Principal saw in the preview: an assignment id, or None for nobody."""
    value = post.get("expected_superseded", "")
    if value == "none":
        return None
    if value.isdigit():
        return int(value)
    raise PreviewOutdated()


@principal_required
@require_http_methods(["GET", "POST"])
def assign(request):
    """
    Assign a committee in two steps. The form posts to a preview that writes
    nothing; the preview's "Issue order" button posts back with step=issue.

    One order may name several people, as the college's real orders do.
    """
    if request.method == "GET":
        return render(
            request,
            "orders/assign.html",
            {
                "form": AssignCommitteeForm(initial={"order_date": timezone.localdate()}),
                "formset": AppointmentFormSet(),
            },
        )

    form = AssignCommitteeForm(request.POST)
    formset = AppointmentFormSet(request.POST)
    step = request.POST.get("step")
    context = {"form": form, "formset": formset}
    if not (form.is_valid() and formset.is_valid()) or step == "edit":
        return render(request, "orders/assign.html", context)

    details = {
        "committee": form.cleaned_data["committee"],
        "appointments": formset.appointments(),
        "order_date": form.cleaned_data["order_date"],
    }
    try:
        if step == "issue":
            order = services.issue_assignment_order(
                **details,
                issued_by=request.user,
                remarks=form.cleaned_data["remarks"],
                references=form.cleaned_data["references"],
                expected_superseded_id=_expected_superseded_id(request.POST),
                request=request,
            )
            messages.success(request, _("Order issued."))
            return redirect("orders:detail", pk=order.pk)
        preview = services.preview_assignment_order(**details, issued_by=request.user)
    except DomainError as exc:
        row = getattr(exc, "appointment_index", None)
        rows = formset.forms
        if row is not None and row < len(rows):
            rows[row].add_error(None, exc.message)
        else:
            form.add_error(None, exc.message)
        return render(request, "orders/assign.html", context)
    context["preview"] = preview
    context["appointments"] = [
        {
            "holder": holder,
            "role": AssignmentRole(role).label,
            "detail": _describe(holder),
        }
        for holder, role in details["appointments"]
    ]
    return render(request, "orders/assign_preview.html", context)


@principal_required
@require_safe
def register(request):
    """Every order ever issued, newest first. Principal only during the sprint."""
    orders = Order.objects.select_related("committee", "academic_year").prefetch_related(
        "created_assignments__faculty"
    )
    return render(request, "orders/register.html", {"orders": list(orders)})


@login_required
@require_safe
def detail(request, pk):
    """One order, resolved through visible_to(): 404 for anyone not entitled to it."""
    order = get_object_or_404(
        Order.objects.visible_to(request.user).select_related(
            "committee", "academic_year", "issued_by", "template_used"
        ),
        pk=pk,
    )
    context = {
        "order": order,
        "created": list(
            order.created_assignments.select_related(
                "faculty__department", "external_member"
            ).order_by("pk")
        ),
        "ended": list(order.ended_assignments.select_related("faculty")),
    }
    return render(request, "orders/detail.html", context)


@login_required
@require_GET
def download(request, pk):
    """
    Serve the stored order file, exactly as issued, to someone entitled to it.

    Never served from MEDIA_URL (docs/03_SECURITY.md §3). Everyone else gets
    404, so the order's existence is not confirmed.
    """
    order = get_object_or_404(Order.objects.visible_to(request.user), pk=pk)
    audit.log(
        action=AuditAction.ORDER_DOWNLOADED,
        obj=order,
        summary=f"{order.order_no} downloaded by {request.user.full_name}",
        request=request,
    )
    response = FileResponse(
        order.generated_file.open("rb"),
        as_attachment=True,
        filename=f"{order.order_no.replace('/', '-')}.docx",
        content_type=DOCX_CONTENT_TYPE,
    )
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@principal_required
@require_http_methods(["GET", "POST"])
def cancel(request, pk):
    """Withdraw an order by issuing a corrigendum. Requires a typed reason."""
    order = get_object_or_404(
        Order.objects.select_related("committee").filter(is_cancelled=False), pk=pk
    )
    form = CancelOrderForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            corrigendum = services.cancel_order(
                order=order,
                reason=form.cleaned_data["reason"],
                issued_by=request.user,
                request=request,
            )
        except DomainError as exc:
            form.add_error(None, exc.message)
        else:
            messages.success(request, _("Order cancelled."))
            return redirect("orders:detail", pk=corrigendum.pk)
    context = {
        "order": order,
        "form": form,
        "created": list(order.created_assignments.select_related("faculty", "committee")),
        "restored": list(
            order.ended_assignments.select_related("faculty", "committee").filter(
                status=AssignmentStatus.SUPERSEDED
            )
        ),
    }
    return render(request, "orders/cancel.html", context)


@principal_required
@require_http_methods(["GET", "POST"])
def relinquish(request, pk):
    """
    Remove someone from a committee, with nobody replacing them, by order
    (BR-4). Nothing is erased: the role ends and moves to their past committees.
    """
    assignment = get_object_or_404(
        Assignment.objects.active().select_related("faculty", "committee"), pk=pk
    )
    form = RelinquishForm(request.POST or None, initial={"order_date": timezone.localdate()})
    if request.method == "POST" and form.is_valid():
        try:
            order = services.issue_relinquishment_order(
                assignment=assignment,
                order_date=form.cleaned_data["order_date"],
                issued_by=request.user,
                remarks=form.cleaned_data["remarks"],
                request=request,
            )
        except DomainError as exc:
            form.add_error(None, exc.message)
        else:
            messages.success(
                request,
                _("%(name)s removed from %(committee)s by order %(number)s.")
                % {
                    "name": assignment.holder_name,
                    "committee": assignment.committee.name,
                    "number": order.order_no,
                },
            )
            back = request.POST.get("next", "")
            if url_has_allowed_host_and_scheme(back, allowed_hosts={request.get_host()}):
                return redirect(back)
            return redirect("orders:detail", pk=order.pk)
    context = {"assignment": assignment, "form": form, "next": request.GET.get("next", "")}
    return render(request, "orders/relinquish.html", context)
