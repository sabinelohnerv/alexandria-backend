from django.db import models
from django.utils import timezone

class PendingRegistration(models.Model):
    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=120)
    last_name = models.CharField(max_length=120)
    password_hash = models.CharField(max_length=256)
    otp_code = models.CharField(max_length=6)
    otp_sent_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    intended_role = models.CharField(max_length=10, default="user")
    is_verified = models.BooleanField(default=False)

    resend_count = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["email"]),
            models.Index(fields=["expires_at"]),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.email} (expires {self.expires_at})"