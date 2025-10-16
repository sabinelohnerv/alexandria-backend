from django.contrib import admin
from .models import RankingWeights, RankingDecision, Feedback, ExperimentAssignment

@admin.register(RankingWeights)
class RankingWeightsAdmin(admin.ModelAdmin):
    list_display = ("version","is_active","created_at")
    readonly_fields = ("created_at",)
    list_filter = ("is_active",)

@admin.register(RankingDecision)
class RankingDecisionAdmin(admin.ModelAdmin):
    list_display = ("query_id","hit_id","model_version","shown_pos","rank_before","rank_after","ts")
    list_filter = ("model_version",)
    search_fields = ("query_id","hit_id")

@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = ("query_id","hit_id","type","value","ts")
    list_filter = ("type",)
    search_fields = ("query_id","hit_id")

@admin.register(ExperimentAssignment)
class ExperimentAssignmentAdmin(admin.ModelAdmin):
    list_display = ("query_id","bucket","weights_version","ts")
    list_filter = ("bucket",)
    search_fields = ("query_id",)
