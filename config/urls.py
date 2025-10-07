from django.contrib import admin
from django.urls import path, include
from django.http import HttpResponse

def healthz(_): return HttpResponse("ok")

urlpatterns = [
    path("healthz", healthz),
    path("admin/", admin.site.urls),
    path("api/", include("staff_whitelist.urls")),
    path("api/auth/", include("accounts_signup.urls")),
    path("api/auth/", include("accounts_auth.urls")),
    path("api/auth/", include("accounts_password.urls")),
    path("api/search/", include("search.urls")),
]

