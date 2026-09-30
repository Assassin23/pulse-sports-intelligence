"""Auth URL patterns."""
from django.urls import path

from sports_platform.users.views.auth_views import (
    LoginView,
    LogoutView,
    RegisterView,
    TokenRefreshViewCustom,
)

app_name = "auth"

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("refresh/", TokenRefreshViewCustom.as_view(), name="refresh"),
]
