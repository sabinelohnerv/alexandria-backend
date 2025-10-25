"""
Script maestro que ejecuta el ciclo completo de entrenamiento.
Ejecuta todos los pasos en secuencia con confirmaciones del usuario.
"""
import os
import sys
import django
from pathlib import Path
import subprocess

# Setup Django
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.ranking_adaptive.models import RankingWeights

def print_header(text):
    """Print a formatted header"""
    print("\n" + "="*80)
    print(f"  {text}")
    print("="*80 + "\n")

def ask_confirmation(question):
    """Ask for user confirmation"""
    while True:
        response = input(f"{question} (s/n): ").lower().strip()
        if response in ['s', 'si', 'sí', 'y', 'yes']:
            return True
        elif response in ['n', 'no']:
            return False
        print("Por favor responde 's' o 'n'")

def run_script(script_name, description):
    """Run a Python script"""
    print(f"\n▶️  Ejecutando: {description}")
    print(f"   Script: {script_name}")
    print("-" * 80)
    
    result = subprocess.run(
        [sys.executable, script_name],
        cwd=BASE_DIR,
        capture_output=False
    )
    
    if result.returncode != 0:
        print(f"\n❌ Error ejecutando {script_name}")
        return False
    
    print(f"\n✅ Completado: {description}")
    return True

def main():
    """Main workflow"""
    
    print_header("🚀 CICLO COMPLETO DE ENTRENAMIENTO - RANKING ADAPTATIVO")
    
    print("Este script ejecutará el ciclo completo de entrenamiento:")
    print("  1. Verificar datos disponibles")
    print("  2. Entrenar múltiples versiones")
    print("  3. Evaluar y comparar versiones")
    print("  4. Analizar pesos")
    print("  5. Activar mejor versión (con confirmación)")
    print("  6. Verificar deployment")
    
    if not ask_confirmation("\n¿Deseas continuar?"):
        print("\n❌ Proceso cancelado por el usuario.")
        return
    
    # Step 1: Check training data
    print_header("PASO 1/6: Verificar Datos de Entrenamiento")
    
    if not run_script("scripts/check_training_data.py", "Verificación de datos"):
        return
    
    if not ask_confirmation("\n¿Los datos son suficientes para continuar?"):
        print("\n⚠️  Proceso detenido. Acumula más feedbacks antes de entrenar.")
        return
    
    # Step 2: Train multiple versions
    print_header("PASO 2/6: Entrenar Múltiples Versiones")
    
    print("⏱️  Este paso puede tomar 2-5 minutos...")
    
    if not ask_confirmation("¿Iniciar entrenamiento?"):
        print("\n❌ Entrenamiento cancelado.")
        return
    
    if not run_script("scripts/train_multiple_versions.py", "Entrenamiento de versiones"):
        return
    
    # Step 3: Test weight versions
    print_header("PASO 3/6: Evaluar y Comparar Versiones")
    
    if not run_script("scripts/test_weight_versions.py", "Evaluación de versiones"):
        return
    
    # Step 4: Analyze weights
    print_header("PASO 4/6: Analizar Pesos")
    
    if not run_script("scripts/analyze_weights.py", "Análisis de pesos"):
        return
    
    # Step 5: Activate best version
    print_header("PASO 5/6: Activar Mejor Versión")
    
    # Get the best version from recent training
    recent_versions = RankingWeights.objects.filter(
        version__startswith='balanced_'
    ).order_by('-created_at')[:3]
    
    if not recent_versions.exists():
        print("❌ No se encontraron versiones recientes para activar.")
        return
    
    print("\nVersiones recientes disponibles:")
    for i, v in enumerate(recent_versions, 1):
        status = "ACTIVA" if v.is_active else "inactiva"
        print(f"  {i}. {v.version} ({status})")
    
    print(f"\nRecomendación: Activar '{recent_versions[0].version}'")
    
    if ask_confirmation(f"\n¿Activar la versión '{recent_versions[0].version}'?"):
        from django.core.management import call_command
        
        try:
            call_command('activate_ranking_weights', recent_versions[0].version)
            print(f"\n✅ Versión '{recent_versions[0].version}' activada exitosamente!")
        except Exception as e:
            print(f"\n❌ Error al activar versión: {e}")
            return
    else:
        print("\n⚠️  Activación omitida. Puedes activar manualmente más tarde con:")
        print(f"   python manage.py activate_ranking_weights {recent_versions[0].version}")
    
    # Step 6: Verify deployment
    print_header("PASO 6/6: Verificar Deployment")
    
    if not run_script("scripts/verify_deployment.py", "Verificación de deployment"):
        return
    
    # Final summary
    print_header("✅ CICLO DE ENTRENAMIENTO COMPLETADO")
    
    print("Próximos pasos recomendados:")
    print("\n1. Monitorear rendimiento:")
    print("   python manage.py report_adaptive_metrics --hours 24")
    print("\n2. Leer documentación completa:")
    print("   scripts/RESUMEN_EJECUTIVO.md")
    print("   scripts/TRAINING_REPORT.md")
    print("\n3. Continuar recolectando feedback para futuro entrenamiento")
    
    print("\n" + "="*80)
    print("🎉 ¡Entrenamiento exitoso! El sistema está listo para producción.")
    print("="*80 + "\n")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n❌ Proceso interrumpido por el usuario.")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Error inesperado: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
