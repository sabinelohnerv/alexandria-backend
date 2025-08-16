from django.urls import path
from .views import JWTLoginView, JWTRefreshView, MeView, JWTLogoutView

urlpatterns = [
    path("login/", JWTLoginView.as_view(), name="jwt-login"),
    path("refresh/", JWTRefreshView.as_view(), name="jwt-refresh"),
    path("me/", MeView.as_view(), name="auth-me"),
    path("logout/", JWTLogoutView.as_view(), name="jwt-logout"), 
]
