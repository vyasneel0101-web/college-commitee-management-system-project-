from django.urls import path

from . import views

app_name = "assignments"

urlpatterns = [
    path("dashboard/", views.dashboard, name="dashboard"),
    path("directory/", views.directory, name="directory"),
]
