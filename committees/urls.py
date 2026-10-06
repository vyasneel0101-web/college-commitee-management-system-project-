from django.urls import path

from . import views

app_name = "committees"

urlpatterns = [
    path("committees/", views.committee_list, name="list"),
    path("committees/new/", views.committee_create, name="create"),
    path("committees/<int:pk>/", views.committee_detail, name="detail"),
    path("committees/<int:pk>/edit/", views.committee_edit, name="edit"),
    path("committees/<int:pk>/template/", views.committee_template_upload, name="template"),
]
