from django.contrib.auth import views as auth_views
from django.urls import path

from . import views
from .forms import EmailAuthenticationForm

app_name = "accounts"

urlpatterns = [
    path(
        "login/",
        auth_views.LoginView.as_view(
            template_name="accounts/login.html",
            authentication_form=EmailAuthenticationForm,
            redirect_authenticated_user=True,
        ),
        name="login",
    ),
    # Django's LogoutView accepts POST only.
    path("auth/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("profile/", views.profile, name="profile"),
    path("workload/", views.workload, name="workload"),
    path("faculty/", views.faculty_list, name="faculty_list"),
    path("faculty/new/", views.faculty_create, name="faculty_create"),
    path("faculty/<int:pk>/", views.faculty_detail, name="faculty_detail"),
    path("faculty/<int:pk>/edit/", views.faculty_edit, name="faculty_edit"),
    path("faculty/<int:pk>/deactivate/", views.faculty_deactivate, name="faculty_deactivate"),
]
