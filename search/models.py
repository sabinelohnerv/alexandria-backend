from django.conf import settings
from django.db import models

User = settings.AUTH_USER_MODEL

class ChatSession(models.Model):
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="chat_sessions")
    title = models.CharField(max_length=200, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-id"]

    def __str__(self):
        return self.title or f"Session #{self.pk}"


class ChatMessage(models.Model):
    ROLE_USER = "user"
    ROLE_ASSISTANT = "assistant"
    ROLE_SYSTEM = "system"
    ROLE_CHOICES = [
        (ROLE_USER, "user"),
        (ROLE_ASSISTANT, "assistant"),
        (ROLE_SYSTEM, "system"),
    ]

    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=16, choices=ROLE_CHOICES)
    text = models.TextField()
    answer_json = models.JSONField(null=True, blank=True)  # citas, layout, etc.
    latency_ms = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]


class SearchHit(models.Model):
    message = models.ForeignKey(ChatMessage, on_delete=models.CASCADE, related_name="hits")
    document = models.ForeignKey("documents.Document", on_delete=models.CASCADE, related_name="hits")
    chunk = models.ForeignKey("documents.Chunk", on_delete=models.CASCADE, related_name="hits")
    rank = models.PositiveIntegerField()
    score_vector = models.FloatField()
    score_lexical = models.FloatField(null=True, blank=True)
    score_rerank = models.FloatField(null=True, blank=True)
    meta_json = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["rank"]
        indexes = [
            models.Index(fields=["message", "rank"]),
            models.Index(fields=["document"]),
            models.Index(fields=["chunk"]),
        ]


class Feedback(models.Model):
    LABEL_USEFUL = "useful"
    LABEL_NOT_USEFUL = "not_useful"
    LABEL_CHOICES = [
        (LABEL_USEFUL, "useful"),
        (LABEL_NOT_USEFUL, "not_useful"),
    ]

    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="feedbacks")
    message = models.ForeignKey(ChatMessage, null=True, blank=True, on_delete=models.CASCADE, related_name="feedbacks")
    hit = models.ForeignKey(SearchHit, null=True, blank=True, on_delete=models.CASCADE, related_name="feedbacks")

    label = models.CharField(max_length=16, choices=LABEL_CHOICES)
    comment = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            # Al menos uno de (message, hit)
            models.CheckConstraint(
                check=(
                    models.Q(message__isnull=False) | models.Q(hit__isnull=False)
                ),
                name="feedback_requires_message_or_hit",
            )
        ]
        ordering = ["-id"]
