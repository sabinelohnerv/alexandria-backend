from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.http import JsonResponse
from django.core.management import call_command
from io import StringIO
import json
from apps.ranking_adaptive.models import RankingWeights


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
