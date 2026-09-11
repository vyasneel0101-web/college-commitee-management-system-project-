from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods, require_safe

from assignments.models import Assignment

from . import services
from .forms import ProfileForm
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
