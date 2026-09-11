from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def principal_required(view_func):
    """
    Anonymous users are sent to sign in; signed-in users who are not the
    Principal get 403, never a redirect (docs/03_SECURITY.md §2).
    """

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_principal:
            raise PermissionDenied
        return view_func(request, *args, **kwargs)

    return login_required(_wrapped)
