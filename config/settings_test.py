from .settings import *

# DB liviana para tests
DATABASES["default"] = {
    "ENGINE": "django.db.backends.sqlite3",
    "NAME": ":memory:",
}

# Solo lo mínimo + tu app
INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "rest_framework",
    "apps.staff_whitelist",
    "apps.accounts_signup",
    "apps.accounts_auth",
    "apps.accounts_password",
]

ALLOWED_HOSTS = ["testserver", "localhost"]

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": [],
}
