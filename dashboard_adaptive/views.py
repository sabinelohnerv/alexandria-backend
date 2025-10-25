from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import user_passes_test
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods, require_POST, require_GET
from django.db.models import Count, Q, Avg
from django.utils import timezone
from datetime import timedelta
import json
from typing import Dict, List, Any

from apps.ranking_adaptive.models import RankingWeights, RankingDecision, ExperimentAssignment
from apps.search.models import Feedback, SearchHit, ChatMessage
from apps.ranking_adaptive.utils import build_pairwise_dataset
from apps.ranking_adaptive.tasks import train_signal_weights
from apps.search.services.ranking.signals import SIGNAL_ORDER

# Decorator for staff-only access
def staff_required(function):
    return user_passes_test(lambda u: u.is_staff)(function)


# ============================================================
# HOME DASHBOARD
# ============================================================

@staff_required
def home(request):
    """Main dashboard with KPIs and quick actions."""
    hours = int(request.GET.get('hours', 24))
    cutoff = timezone.now() - timedelta(hours=hours)
    
    # Get KPIs by bucket
    buckets_data = _get_kpis_by_bucket(cutoff)
    
    # Recent assignments
    recent_assignments = ExperimentAssignment.objects.order_by('-ts')[:10]
    
    # Active version
    active_version = RankingWeights.objects.filter(is_active=True).first()
    
    # Total counts
    total_decisions = RankingDecision.objects.filter(ts__gte=cutoff).count()
    total_feedback = Feedback.objects.filter(created_at__gte=cutoff).count()
    
    context = {
        'hours': hours,
        'buckets_data': buckets_data,
        'recent_assignments': recent_assignments,
        'active_version': active_version,
        'total_decisions': total_decisions,
        'total_feedback': total_feedback,
    }
    
    return render(request, 'dashboard_adaptive/home.html', context)


def _get_kpis_by_bucket(cutoff):
    """Calculate KPIs for each bucket."""
    buckets = ['control', 'treatment', 'shadow']
    data = {}
    
    for bucket in buckets:
        # Get hits in this bucket
        hits = SearchHit.objects.filter(
            created_at__gte=cutoff,
            rank__lte=10
        ).filter(
            Q(meta_json__experiment_bucket=bucket) |
            Q(meta_json__contains={'experiment_bucket': bucket})
        )
        
        total_hits = hits.count()
        
        # Count useful feedback
        useful_count = Feedback.objects.filter(
            hit__in=hits,
            label=Feedback.LABEL_USEFUL,
            created_at__gte=cutoff
        ).count()
        
        # Count queries
        query_count = hits.values('message_id').distinct().count()
        
        # Count all feedback
        feedback_count = Feedback.objects.filter(
            hit__in=hits,
            created_at__gte=cutoff
        ).count()
        
        # Calculate useful@10
        useful_at_10 = (useful_count / total_hits * 100) if total_hits > 0 else 0
        
        data[bucket] = {
            'useful_at_10': useful_at_10,
            'useful_count': useful_count,
            'total_hits': total_hits,
            'query_count': query_count,
            'feedback_count': feedback_count,
        }
    
    return data


# ============================================================
# TRAINING & DATASET
# ============================================================

@staff_required
@require_POST
def train_weights(request):
    """Trigger Celery task to train weights."""
    days = int(request.POST.get('days', 30))
    lr = float(request.POST.get('lr', 0.01))
    steps = int(request.POST.get('steps', 2000))
    l2 = float(request.POST.get('l2', 0.05))
    
    try:
        # Enqueue task
        task = train_signal_weights.delay(
            days=days,
            lr=lr,
            steps=steps,
            l2=l2
        )
        
        return JsonResponse({
            'success': True,
            'message': f'Training task enqueued: {task.id}',
            'task_id': task.id
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Error: {str(e)}'
        }, status=500)


@staff_required
@require_GET
def dataset_info(request):
    """Show dataset info (dry-run)."""
    days = int(request.GET.get('days', 30))
    
    try:
        ds = build_pairwise_dataset(days=days)
        
        data = {
            'n_pairs': ds.n_pairs,
            'n_queries': ds.n_queries,
            'dim': ds.dim,
            'shape': str(ds.Xdiff.shape) if ds.Xdiff is not None else 'N/A',
            'days': days,
        }
        
        if request.headers.get('HX-Request'):
            return render(request, 'dashboard_adaptive/partials/dataset_info.html', data)
        
        return JsonResponse(data)
    except Exception as e:
        return JsonResponse({
            'error': str(e)
        }, status=500)


# ============================================================
# WEIGHTS MANAGEMENT
# ============================================================

@staff_required
def weights_list(request):
    """List all weight versions with filters."""
    # Filters
    version_filter = request.GET.get('version', '')
    active_filter = request.GET.get('active', '')
    
    weights = RankingWeights.objects.all().order_by('-created_at')
    
    if version_filter:
        weights = weights.filter(version__icontains=version_filter)
    
    if active_filter == 'true':
        weights = weights.filter(is_active=True)
    elif active_filter == 'false':
        weights = weights.filter(is_active=False)
    
    # Pagination (simple)
    page = int(request.GET.get('page', 1))
    per_page = 20
    start = (page - 1) * per_page
    end = start + per_page
    
    weights_page = weights[start:end]
    has_next = weights.count() > end
    
    context = {
        'weights': weights_page,
        'version_filter': version_filter,
        'active_filter': active_filter,
        'page': page,
        'has_next': has_next,
    }
    
    if request.headers.get('HX-Request'):
        return render(request, 'dashboard_adaptive/partials/weights_table.html', context)
    
    return render(request, 'dashboard_adaptive/weights_list.html', context)


@staff_required
@require_POST
def promote_weight(request):
    """Promote (activate) a weight version."""
    version = request.POST.get('version')
    
    if not version:
        return JsonResponse({'success': False, 'message': 'Version required'}, status=400)
    
    try:
        # Deactivate all
        RankingWeights.objects.update(is_active=False)
        
        # Activate selected
        weight = RankingWeights.objects.get(version=version)
        weight.is_active = True
        weight.save()
        
        if request.headers.get('HX-Request'):
            # Return updated row
            return render(request, 'dashboard_adaptive/partials/weight_row.html', {
                'weight': weight
            })
        
        return JsonResponse({
            'success': True,
            'message': f'Activated version: {version}'
        })
    except RankingWeights.DoesNotExist:
        return JsonResponse({
            'success': False,
            'message': f'Version not found: {version}'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=500)


@staff_required
@require_POST
def rollback_weight(request):
    """Rollback to a previous version."""
    version = request.POST.get('version')
    
    if not version:
        return JsonResponse({'success': False, 'message': 'Version required'}, status=400)
    
    try:
        # Same as promote
        RankingWeights.objects.update(is_active=False)
        weight = RankingWeights.objects.get(version=version)
        weight.is_active = True
        weight.save()
        
        return JsonResponse({
            'success': True,
            'message': f'Rolled back to version: {version}'
        })
    except RankingWeights.DoesNotExist:
        return JsonResponse({
            'success': False,
            'message': f'Version not found: {version}'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=500)


@staff_required
def weight_detail(request, version):
    """Show weight detail in modal."""
    weight = get_object_or_404(RankingWeights, version=version)
    
    # Prepare weights with signal names
    weights_data = []
    for i, (signal_name, w) in enumerate(zip(SIGNAL_ORDER, weight.weights)):
        weights_data.append({
            'index': i,
            'signal': signal_name,
            'weight': w,
            'bar_width': int(abs(w) * 200),  # Scale for CSS bar
        })
    
    context = {
        'weight': weight,
        'weights_data': weights_data,
        'weights_json': json.dumps(weight.weights),
    }
    
    return render(request, 'dashboard_adaptive/partials/weight_detail.html', context)


# ============================================================
# QUERY EXPLORER
# ============================================================

@staff_required
def query_explorer(request):
    """Search and explore queries with explain."""
    message_id = request.GET.get('message_id', '')
    query_text = request.GET.get('q', '')
    date_from = request.GET.get('from', '')
    date_to = request.GET.get('to', '')
    
    hits = SearchHit.objects.select_related('message').filter(rank__lte=10).order_by('-created_at')
    
    # Filters
    if message_id:
        hits = hits.filter(message_id=int(message_id))
    
    if query_text:
        hits = hits.filter(message__content__icontains=query_text)
    
    if date_from:
        hits = hits.filter(created_at__gte=date_from)
    
    if date_to:
        hits = hits.filter(created_at__lte=date_to)
    
    # Limit results
    hits = hits[:20]
    
    context = {
        'hits': hits,
        'message_id': message_id,
        'query_text': query_text,
        'date_from': date_from,
        'date_to': date_to,
    }
    
    return render(request, 'dashboard_adaptive/query_explorer.html', context)


@staff_required
def query_explain(request, message_id):
    """Explain signals for a specific query (HTMX partial)."""
    hits = SearchHit.objects.filter(
        message_id=message_id,
        rank__lte=10
    ).order_by('rank')
    
    # Get active weights
    active_weight = RankingWeights.objects.filter(is_active=True).first()
    weights = active_weight.weights if active_weight else [0.0] * len(SIGNAL_ORDER)
    
    # Prepare explain data
    explain_data = []
    for hit in hits:
        meta = hit.meta_json or {}
        signals = meta.get('signals', {})
        
        # Extract signal values
        signal_values = []
        for signal_name in SIGNAL_ORDER:
            value = signals.get(signal_name, 0.0)
            # Convert boolean to float
            if isinstance(value, bool):
                value = 1.0 if value else 0.0
            signal_values.append(value)
        
        # Calculate contributions
        contributions = []
        total_signal_contrib = 0.0
        
        for i, (signal_name, x, w) in enumerate(zip(SIGNAL_ORDER, signal_values, weights)):
            contrib = w * x
            total_signal_contrib += contrib
            contributions.append({
                'signal': signal_name,
                'x': x,
                'w': w,
                'contrib': contrib,
            })
        
        # Get CE score and alpha
        score_ce = meta.get('rerank_ce', 0.0)
        final_score = meta.get('final_score', 0.0)
        
        # Infer alpha (assuming final = alpha * CE + sum(w*x))
        alpha = (final_score - total_signal_contrib) / score_ce if score_ce > 0 else 1.0
        
        explain_data.append({
            'hit': hit,
            'contributions': contributions,
            'score_ce': score_ce,
            'alpha': alpha,
            'alpha_ce': alpha * score_ce,
            'total_signal': total_signal_contrib,
            'final_score': final_score,
            'bucket': meta.get('experiment_bucket', 'N/A'),
            'version': meta.get('weights_version_used', 'N/A'),
        })
    
    context = {
        'message_id': message_id,
        'explain_data': explain_data,
        'signal_names': SIGNAL_ORDER,
    }
    
    return render(request, 'dashboard_adaptive/partials/query_explain.html', context)


# ============================================================
# A/B METRICS
# ============================================================

@staff_required
def ab_metrics(request):
    """Show A/B metrics by bucket."""
    hours = int(request.GET.get('hours', 24))
    cutoff = timezone.now() - timedelta(hours=hours)
    
    # Get detailed metrics by bucket
    buckets_data = _get_detailed_metrics(cutoff)
    
    # Calculate z-test for control vs treatment
    z_test_result = _calculate_z_test(
        buckets_data.get('control', {}),
        buckets_data.get('treatment', {})
    )
    
    context = {
        'hours': hours,
        'buckets_data': buckets_data,
        'z_test': z_test_result,
    }
    
    if request.headers.get('HX-Request'):
        return render(request, 'dashboard_adaptive/partials/ab_metrics.html', context)
    
    return render(request, 'dashboard_adaptive/ab_metrics.html', context)


def _get_detailed_metrics(cutoff):
    """Get detailed metrics for each bucket."""
    buckets = ['control', 'treatment', 'shadow']
    data = {}
    
    for bucket in buckets:
        hits = SearchHit.objects.filter(
            created_at__gte=cutoff,
            rank__lte=10
        ).filter(
            Q(meta_json__experiment_bucket=bucket) |
            Q(meta_json__contains={'experiment_bucket': bucket})
        )
        
        total_hits = hits.count()
        
        # Feedback counts
        useful = Feedback.objects.filter(
            hit__in=hits,
            label=Feedback.LABEL_USEFUL,
            created_at__gte=cutoff
        ).count()
        
        not_useful = Feedback.objects.filter(
            hit__in=hits,
            label=Feedback.LABEL_NOT_USEFUL,
            created_at__gte=cutoff
        ).count()
        
        # Queries
        queries = hits.values('message_id').distinct().count()
        
        # useful@10
        useful_at_10 = (useful / total_hits * 100) if total_hits > 0 else 0
        
        data[bucket] = {
            'total_hits': total_hits,
            'useful': useful,
            'not_useful': not_useful,
            'queries': queries,
            'useful_at_10': useful_at_10,
        }
    
    return data


def _calculate_z_test(control_data, treatment_data):
    """Simple z-test for two proportions."""
    if not control_data or not treatment_data:
        return None
    
    n1 = control_data.get('total_hits', 0)
    n2 = treatment_data.get('total_hits', 0)
    x1 = control_data.get('useful', 0)
    x2 = treatment_data.get('useful', 0)
    
    if n1 == 0 or n2 == 0:
        return None
    
    p1 = x1 / n1
    p2 = x2 / n2
    
    # Pooled proportion
    p_pool = (x1 + x2) / (n1 + n2)
    
    # Standard error
    se = (p_pool * (1 - p_pool) * (1/n1 + 1/n2)) ** 0.5
    
    if se == 0:
        return None
    
    # Z-score
    z = (p2 - p1) / se
    
    # Approximate p-value (two-tailed)
    from math import erf, sqrt
    p_value = 2 * (1 - 0.5 * (1 + erf(abs(z) / sqrt(2))))
    
    return {
        'p1': p1 * 100,
        'p2': p2 * 100,
        'diff': (p2 - p1) * 100,
        'z_score': z,
        'p_value': p_value,
        'significant': p_value < 0.05,
    }
