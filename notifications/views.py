from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.views.decorators.http import require_safe

from . import services


@login_required
@require_safe
def notification_list(request):
    """
    Your own notifications, newest first. Opening the page marks them read;
    the ones that were unread are still highlighted on this visit.
    """
    notifications = list(
        request.user.notifications.select_related("committee", "order")[:100]
    )
    unread_ids = {n.pk for n in notifications if n.is_unread}
    services.mark_all_read(request.user)
    return render(
        request,
        "notifications/list.html",
        {"notifications": notifications, "unread_ids": unread_ids},
    )
