def unread_count(request):
    """Unread notifications for the header link. One small query per signed-in page."""
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {}
    return {"unread_notifications": user.notifications.unread().count()}
