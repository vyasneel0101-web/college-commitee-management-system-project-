from django.shortcuts import render
from django.views.decorators.http import require_safe


@require_safe
def index(request):
    """
    Public landing page with a sign-in button.

    One of only two views reachable without login during the sprint
    (docs/03_SECURITY.md). It must never render data from the database.
    """
    return render(request, "core/index.html")
