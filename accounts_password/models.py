from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()

class PasswordResetTicket(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="password_reset_tickets")
    email = models.EmailField()  
    otp_code = models.CharField(max_length=6)
    otp_sent_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    resend_count = models.PositiveIntegerField(default=0)
    is_used = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["email"]),
            models.Index(fields=["expires_at"]),
            models.Index(fields=["is_used"]),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"PasswordResetTicket<{self.email}> used={self.is_used}"
