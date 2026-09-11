from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_http_methods, require_safe

from accounts.decorators import principal_required
from audit import services as audit
from audit.models import AuditAction
from core.exceptions import DomainError, PreviewOutdated

from . import services
from .forms import AssignCommitteeForm
from .models import Order

DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


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
    """
    if request.method == "GET":
        form = AssignCommitteeForm(initial={"order_date": timezone.localdate()})
        return render(request, "orders/assign.html", {"form": form})

    form = AssignCommitteeForm(request.POST)
    step = request.POST.get("step")
    if not form.is_valid() or step == "edit":
        return render(request, "orders/assign.html", {"form": form})

    details = {key: form.cleaned_data[key] for key in ("committee", "faculty", "role", "order_date")}
    try:
        if step == "issue":
            order = services.issue_assignment_order(
                **details,
                issued_by=request.user,
                remarks=form.cleaned_data["remarks"],
                expected_superseded_id=_expected_superseded_id(request.POST),
                request=request,
            )
            messages.success(request, _("Order issued."))
            return redirect("orders:detail", pk=order.pk)
        preview = services.preview_assignment_order(**details, issued_by=request.user)
    except DomainError as exc:
        form.add_error(None, exc.message)
        return render(request, "orders/assign.html", {"form": form})
    return render(request, "orders/assign_preview.html", {"form": form, "preview": preview})


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
        "created": list(order.created_assignments.select_related("faculty__department")),
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
