from django.conf import settings
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path(settings.ADMIN_URL, admin.site.urls),
    path("", include("accounts.urls")),
    path("", include("assignments.urls")),
    path("", include("orders.urls")),
    path("", include("audit.urls")),
    path("", include("core.urls")),
]

# MEDIA_URL is deliberately not routed here, not even under DEBUG. Order
# documents and signatures are served only by permission-checked views.
# docs/03_SECURITY.md §3.
