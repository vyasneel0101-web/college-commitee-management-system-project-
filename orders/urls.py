from django.urls import path

from . import views

app_name = "orders"

urlpatterns = [
    path("assign/", views.assign, name="assign"),
    path("orders/", views.register, name="register"),
    path("orders/<int:pk>/", views.detail, name="detail"),
    path("orders/<int:pk>/download/", views.download, name="download"),
    path("orders/<int:pk>/cancel/", views.cancel, name="cancel"),
    path("assignments/<int:pk>/relinquish/", views.relinquish, name="relinquish"),
]
