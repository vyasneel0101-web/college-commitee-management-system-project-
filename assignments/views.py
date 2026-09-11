from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.views.decorators.http import require_safe

from .forms import DirectoryFilterForm
from .models import Assignment, AssignmentStatus


@login_required
@require_safe
def dashboard(request):
    """The signed-in user's own committees only: those held now, then past ones."""
    mine = Assignment.objects.for_faculty(request.user).select_related(
        "committee", "issuing_order", "superseded_by__faculty"
    )
    context = {
        "active": list(mine.active().order_by("committee__name")),
        "past": list(
            mine.exclude(status=AssignmentStatus.ACTIVE).order_by("-end_date", "-start_date")
        ),
    }
    return render(request, "assignments/dashboard.html", context)


@login_required
@require_safe
def directory(request):
    """Every ACTIVE assignment in the institution, optionally filtered. Read-only."""
    form = DirectoryFilterForm(request.GET)
    query = form.cleaned_data["q"] if form.is_valid() else ""
    context = {
        "form": form,
        "query": query,
        "assignments": list(Assignment.objects.directory().matching(query)),
    }
    return render(request, "assignments/directory.html", context)
