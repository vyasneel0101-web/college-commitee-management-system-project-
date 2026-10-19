from django.shortcuts import redirect, render
from django.views.decorators.http import require_safe


@require_safe
def index(request):
    """
    Public landing page with a sign-in button; signed-in users go to their dashboard.

    One of only two views reachable without login during the sprint
    (docs/03_SECURITY.md). It must never render data from the database.
    """
    if request.user.is_authenticated:
        return redirect("assignments:dashboard")
    return render(request, "core/index.html")
