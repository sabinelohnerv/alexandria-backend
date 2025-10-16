from django.db import models
from django.contrib.postgres.fields import ArrayField
from django.utils import timezone

class RankingWeights(models.Model):
    version = models.CharField(max_length=50, unique=True)
    # vector de pesos en el mismo orden que señales x
    weights = ArrayField(models.FloatField(), help_text="w_i por señal")
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now)
    is_active = models.BooleanField(default=False)

class RankingDecision(models.Model):
    query_id = models.BigIntegerField()
    message_id = models.BigIntegerField(null=True, blank=True)
    hit_id = models.BigIntegerField()
    model_version = models.CharField(max_length=50)
    score_ce = models.FloatField()               # score del cross-encoder
    rank_before = models.IntegerField()
    rank_after  = models.IntegerField()
    shown_pos   = models.IntegerField()
    # vector de señales ya normalizadas [0..1] y en ORDEN fijo
    signals = ArrayField(models.FloatField())
    # opcional: almacena por claridad los nombres de señales
    signal_names = ArrayField(models.CharField(max_length=40), default=list)
    ts = models.DateTimeField(default=timezone.now)

class Feedback(models.Model):
    query_id = models.BigIntegerField()
    hit_id   = models.BigIntegerField()
    type     = models.CharField(max_length=16)  # 'thumb','click','dwell','comment'
    value    = models.FloatField(default=0.0)   # 1/0, segs dwell, etc.
    ts       = models.DateTimeField(default=timezone.now)

class ExperimentAssignment(models.Model):
    query_id = models.BigIntegerField(unique=True)
    bucket   = models.CharField(max_length=16)  # 'control'|'treatment'|'shadow'
    weights_version = models.CharField(max_length=50)
    ts = models.DateTimeField(default=timezone.now)
