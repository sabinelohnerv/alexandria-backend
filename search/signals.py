from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from .models import ChatMessage

@receiver(post_save, sender=ChatMessage)
def bump_session_updated_at(sender, instance: ChatMessage, created, **kwargs):
    if not created:
        return
    session = instance.session
    session.updated_at = timezone.now()
    session.save(update_fields=["updated_at"])
