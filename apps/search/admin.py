from django.contrib import admin
from .models import ChatSession, ChatMessage, SearchHit, Feedback

@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "title", "updated_at")
    search_fields = ("title", "user__email")
    list_filter = ("user",)
    ordering = ("-updated_at",)

@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ("id", "session", "role", "created_at", "latency_ms")
    list_filter = ("role",)
    search_fields = ("text",)

@admin.register(SearchHit)
class SearchHitAdmin(admin.ModelAdmin):
    list_display = ("id", "message", "document", "chunk", "rank", "score_vector")
    list_filter = ("rank",)
    search_fields = ("document__title", "chunk__section")

@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "label", "message", "hit", "created_at")
    list_filter = ("label",)
    search_fields = ("comment",)
