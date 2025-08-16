from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("staff_whitelist.urls")),
    path("api/auth/", include("accounts_signup.urls")),
    path("api/auth/", include("accounts_auth.urls")),
    path("api/auth/", include("accounts_password.urls")),
]

