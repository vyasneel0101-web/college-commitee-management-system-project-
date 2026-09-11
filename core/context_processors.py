from django.conf import settings


def institution(request):
    """
    Institution identity and the demo-mode flag for every template.

    The demo banner in base.html depends on `demo_mode`; removing it from this
    context silently removes the banner. docs/08_DEMO_DATA.md §1.
    """
    return {
        "institution_name": settings.INSTITUTION_NAME,
        "institution_code": settings.INSTITUTION_CODE,
        "demo_mode": settings.DEMO_MODE,
        "login_url": settings.LOGIN_URL,
    }
