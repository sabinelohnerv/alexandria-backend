from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import StaffWhitelist

@receiver(post_save, sender=StaffWhitelist)
def log_whitelist_change(sender, instance, created, **kwargs):
    action = "CREATED" if created else "UPDATED"
    print(f"[WHITELIST LOG] {action}: {instance}")