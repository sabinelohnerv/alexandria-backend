from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.http import JsonResponse
from django.core.management import call_command
from django.core.paginator import Paginator
from io import StringIO
import json
from apps.ranking_adaptive.models import RankingWeights, RankingDecision
from apps.search.models import ChatMessage, SearchHit


def is_staff(user):
    return user.is_staff


@login_required
@user_passes_test(is_staff)
def dashboard_home(request):
    """Vista principal del dashboard"""
    versions = RankingWeights.objects.order_by('-created_at')[:10]
    active_version = RankingWeights.objects.filter(is_active=True).first()
    
    context = {
        'versions': versions,
        'active_version': active_version,
        'total_versions': RankingWeights.objects.count(),
    }
    return render(request, 'ranking_dashboard/home.html', context)


@login_required
@user_passes_test(is_staff)
def train_weights(request):
    """Ejecuta entrenamiento de pesos"""
    if request.method == 'POST':
        try:
            days = int(request.POST.get('days', 30))
            lr = float(request.POST.get('lr', 0.005))
            steps = int(request.POST.get('steps', 800))
            l2 = float(request.POST.get('l2', 0.2))
            
            output = StringIO()
            call_command(
                'train_ranking_weights',
                days=days,
                lr=lr,
                steps=steps,
                l2=l2,
                stdout=output
            )
            
            output_text = output.getvalue()
            
            # Extraer nombre de versión
            version_name = None
            for line in output_text.split('\n'):
                if 'Entrenamiento completado:' in line:
                    version_name = line.split(':')[-1].strip()
                    break
            
            if version_name and version_name != 'NOOP_EMPTY_DATASET':
                messages.success(request, f'Entrenamiento completado: {version_name}')
            else:
                messages.warning(request, 'No hay datos suficientes para entrenar')
            
            return redirect('ranking_dashboard:home')
            
        except Exception as e:
            messages.error(request, f'Error durante entrenamiento: {str(e)}')
            return redirect('ranking_dashboard:home')
    
    return render(request, 'ranking_dashboard/train.html')


@login_required
@user_passes_test(is_staff)
def list_versions(request):
    """Lista versiones de pesos"""
    versions = RankingWeights.objects.order_by('-created_at')[:20]
    return render(request, 'ranking_dashboard/versions.html', {'versions': versions})


@login_required
@user_passes_test(is_staff)
def activate_version(request, version):
    """Activa una versión específica"""
    if request.method == 'POST':
        try:
            call_command('activate_ranking_weights', version)
            messages.success(request, f'Versión activada: {version}')
        except Exception as e:
            messages.error(request, f'Error al activar: {str(e)}')
    
    return redirect('ranking_dashboard:versions')


@login_required
@user_passes_test(is_staff)
def evaluate_version(request, version):
    """Evalúa una versión específica"""
    try:
        output = StringIO()
        call_command(
            'evaluate_ranking_model',
            model_version=version,
            days=7,
            compare=True,
            stdout=output
        )
        
        evaluation_output = output.getvalue()
        
        context = {
            'version': version,
            'evaluation_output': evaluation_output,
        }
        return render(request, 'ranking_dashboard/evaluate.html', context)
        
    except Exception as e:
        messages.error(request, f'Error al evaluar: {str(e)}')
        return redirect('ranking_dashboard:versions')


@login_required
@user_passes_test(is_staff)
def run_full_cycle(request):
    """Ejecuta ciclo completo de entrenamiento"""
    if request.method == 'POST':
        try:
            days = int(request.POST.get('days', 30))
            auto_activate = request.POST.get('auto_activate') == 'on'
            
            output = StringIO()
            call_command(
                'run_training_cycle',
                days=days,
                auto_activate=auto_activate,
                stdout=output
            )
            
            output_text = output.getvalue()
            
            messages.success(request, 'Ciclo de entrenamiento completado')
            
            return render(request, 'ranking_dashboard/cycle_result.html', {
                'output': output_text
            })
            
        except Exception as e:
            messages.error(request, f'Error durante el ciclo: {str(e)}')
            return redirect('ranking_dashboard:home')
    
    return render(request, 'ranking_dashboard/cycle.html')


@login_required
@user_passes_test(is_staff)
def export_data(request):
    """Exporta datos de entrenamiento"""
    if request.method == 'POST':
        try:
            days = int(request.POST.get('days', 30))
            
            output = StringIO()
            call_command(
                'export_training_data',
                output='training_export.json',
                days=days,
                stdout=output
            )
            
            messages.success(request, 'Datos exportados a training_export.json')
            return redirect('ranking_dashboard:home')
            
        except Exception as e:
            messages.error(request, f'Error al exportar: {str(e)}')
            return redirect('ranking_dashboard:home')
    
    return render(request, 'ranking_dashboard/export.html')


@login_required
@user_passes_test(is_staff)
def rollback_version(request):
    """Rollback a versión anterior"""
    if request.method == 'POST':
        try:
            call_command('activate_prev_weights')
            messages.success(request, 'Rollback completado a versión anterior')
        except Exception as e:
            messages.error(request, f'Error al hacer rollback: {str(e)}')
    
    return redirect('ranking_dashboard:versions')


@login_required
@user_passes_test(is_staff)
def explainability_list(request):
    """Lista mensajes recientes para análisis de explicabilidad"""
    # Filtrar mensajes de asistente con latencia registrada
    messages_qs = (ChatMessage.objects
                   .filter(role=ChatMessage.ROLE_ASSISTANT, latency_ms__isnull=False)
                   .select_related('session', 'session__user')
                   .order_by('-created_at'))
    
    # Filtros opcionales
    search_query = request.GET.get('q', '').strip()
    if search_query:
        messages_qs = messages_qs.filter(text__icontains=search_query)
    
    min_latency = request.GET.get('min_latency')
    if min_latency and min_latency.isdigit():
        messages_qs = messages_qs.filter(latency_ms__gte=int(min_latency))
    
    # Paginación
    paginator = Paginator(messages_qs, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'search_query': search_query,
        'min_latency': min_latency,
    }
    return render(request, 'ranking_dashboard/explainability_list.html', context)


@login_required
@user_passes_test(is_staff)
def explainability_detail(request, message_id):
    """Muestra la explicabilidad detallada de un mensaje específico"""
    try:
        message = (ChatMessage.objects
                   .select_related('session', 'session__user')
                   .get(pk=message_id, role=ChatMessage.ROLE_ASSISTANT))
    except ChatMessage.DoesNotExist:
        messages.error(request, 'Mensaje no encontrado')
        return redirect('ranking_dashboard:explainability_list')
    
    # Obtener datos del mensaje
    answer_json = message.answer_json or {}
    timings = answer_json.get('timings', {})
    
    # Obtener query del usuario (mensaje anterior)
    user_message = (message.session.messages
                    .filter(role=ChatMessage.ROLE_USER, created_at__lt=message.created_at)
                    .order_by('-created_at')
                    .first())
    query_text = user_message.text if user_message else ""
    
    # Obtener hits
    hits = (SearchHit.objects
            .filter(message=message)
            .select_related('document', 'chunk')
            .order_by('rank'))
    
    hits_data = []
    for hit in hits:
        meta = hit.meta_json or {}
        hits_data.append({
            'rank': hit.rank,
            'document_title': hit.document.title,
            'chunk_id': hit.chunk_id,
            'section': meta.get('section'),
            'scores': {
                'vector': float(hit.score_vector or 0),
                'lexical': float(meta.get('lex', 0)),
                'base_rrf': float(meta.get('base_rrf', 0)),
                'rerank_ce': meta.get('rerank_ce'),
                'rerank_ce_raw': meta.get('rerank_ce_raw'),
                'final_score': float(meta.get('final_score', 0)),
            },
            'signals': meta.get('signals', {}),
        })
    
    # Obtener decisiones de ranking
    try:
        decisions = (RankingDecision.objects
                    .filter(message_id=message.id)
                    .order_by('shown_pos'))
        
        decisions_data = []
        for dec in decisions:
            rank_change = abs(dec.rank_before - dec.rank_after)
            decisions_data.append({
                'hit_id': dec.hit_id,
                'rank_before': dec.rank_before,
                'rank_after': dec.rank_after,
                'rank_change': rank_change,
                'shown_pos': dec.shown_pos,
                'score_ce': float(dec.score_ce or 0),
                'signals': dec.signals,
                'signal_names': dec.signal_names,
                'model_version': dec.model_version,
            })
    except Exception:
        decisions_data = []
    
    # Preparar fases con tiempos y colores (paleta basada en #023f66)
    phases = [
        {'name': 'Setup', 'key': 'setup_ms', 'duration': timings.get('setup_ms', 0), 'description': 'Creación de sesión y mensaje', 'color': 'bg-phase-1'},
        {'name': 'Embedding', 'key': 'embedding_ms', 'duration': timings.get('embedding_ms', 0), 'description': 'Generación del embedding de la consulta', 'color': 'bg-phase-2'},
        {'name': 'Search', 'key': 'search_ms', 'duration': timings.get('search_ms', 0), 'description': 'Búsqueda vectorial y léxica', 'color': 'bg-phase-3'},
        {'name': 'RRF Fusion', 'key': 'rrf_fusion_ms', 'duration': timings.get('rrf_fusion_ms', 0), 'description': 'Fusión de resultados', 'color': 'bg-phase-4'},
        {'name': 'Retrieve Total', 'key': 'retrieve_total_ms', 'duration': timings.get('retrieve_total_ms', 0), 'description': 'Tiempo total de recuperación', 'color': 'bg-phase-5'},
        {'name': 'Rerank', 'key': 'rerank_ms', 'duration': timings.get('rerank_ms', 0), 'description': 'Reranking con cross-encoder', 'color': 'bg-phase-6'},
        {'name': 'Signals Scoring', 'key': 'signals_scoring_ms', 'duration': timings.get('signals_scoring_ms', 0), 'description': 'Cálculo de señales y scoring', 'color': 'bg-phase-7'},
        {'name': 'MMR', 'key': 'mmr_ms', 'duration': timings.get('mmr_ms', 0), 'description': 'Selección MMR para diversidad', 'color': 'bg-phase-8'},
        {'name': 'LLM Synthesis', 'key': 'llm_synthesis_ms', 'duration': timings.get('llm_synthesis_ms', 0), 'description': 'Generación de respuesta', 'color': 'bg-phase-9'},
        {'name': 'Persistence', 'key': 'persistence_ms', 'duration': timings.get('persistence_ms', 0), 'description': 'Persistencia en BD', 'color': 'bg-phase-10'},
    ]
    
    total_ms = timings.get('total_ms', message.latency_ms)
    
    # Calcular porcentajes
    for phase in phases:
        phase['percentage'] = (phase['duration'] / total_ms * 100) if total_ms > 0 else 0
    
    context = {
        'message': message,
        'query_text': query_text,
        'user_message': user_message,
        'answer_json': answer_json,
        'timings': timings,
        'phases': phases,
        'total_ms': total_ms,
        'hits': hits_data,
        'decisions': decisions_data,
        'configuration': {
            'enable_rerank': answer_json.get('enable_rerank', True),
            'weights': answer_json.get('weights', {}),
            'org_weights': answer_json.get('org_weights', {}),
            'weights_version_used': answer_json.get('weights_version_used', 'active'),
            'experiment_bucket': answer_json.get('experiment_bucket', 'control'),
            'rerank_score_mode': answer_json.get('rerank_score_mode', 'sigmoid_minmax'),
        },
    }
    
    return render(request, 'ranking_dashboard/explainability_detail.html', context)
