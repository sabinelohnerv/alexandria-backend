from django.apps import AppConfig

class StaffWhitelistConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "staff_whitelist"

    def ready(self):
        import staff_whitelist.signals
