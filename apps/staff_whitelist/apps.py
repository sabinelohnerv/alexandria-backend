from django.apps import AppConfig

class StaffWhitelistConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.staff_whitelist"

    def ready(self):
        import apps.staff_whitelist.signals
