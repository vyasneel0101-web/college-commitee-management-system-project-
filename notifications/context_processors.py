def unread_count(request):
    """
    Unread count for the header link. The Principal only sees the link once he
    has been notified of something, since he is notified only about committees
    he is on.
    """
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {}
    unread = user.notifications.unread().count()
    show = unread > 0 or not user.is_principal or user.notifications.exists()
    return {"unread_notifications": unread, "show_notifications_link": show}
