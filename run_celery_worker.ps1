# Script PowerShell para levantar Celery Worker en Windows
# Uso: .\run_celery_worker.ps1

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Celery Worker - Adaptive Ranking" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# Verificar si estamos en el directorio correcto
if (-not (Test-Path "manage.py")) {
    Write-Host "ERROR: No se encuentra manage.py" -ForegroundColor Red
    Write-Host "Ejecuta este script desde la raíz del proyecto Django" -ForegroundColor Yellow
    exit 1
}

# Verificar variables de entorno (opcional)
Write-Host "Configuración:" -ForegroundColor Green
Write-Host "  CELERY_BROKER_URL: $env:CELERY_BROKER_URL" -ForegroundColor Gray
Write-Host "  CELERY_RESULT_BACKEND: $env:CELERY_RESULT_BACKEND" -ForegroundColor Gray
Write-Host ""

# Opciones de pool
Write-Host "Selecciona el modo de ejecución:" -ForegroundColor Yellow
Write-Host "  1) Solo (recomendado para Windows)" -ForegroundColor White
Write-Host "  2) Threads (4 workers)" -ForegroundColor White
Write-Host "  3) Threads (8 workers)" -ForegroundColor White
Write-Host ""

$choice = Read-Host "Opción [1-3]"

switch ($choice) {
    "1" {
        Write-Host "Iniciando worker con pool SOLO..." -ForegroundColor Green
        celery -A config worker -P solo -Q training -n worker-training@$env:COMPUTERNAME -l INFO
    }
    "2" {
        Write-Host "Iniciando worker con pool THREADS (4 workers)..." -ForegroundColor Green
        celery -A config worker --pool threads --concurrency 4 -Q training -n worker-training@$env:COMPUTERNAME -l INFO
    }
    "3" {
        Write-Host "Iniciando worker con pool THREADS (8 workers)..." -ForegroundColor Green
        celery -A config worker --pool threads --concurrency 8 -Q training -n worker-training@$env:COMPUTERNAME -l INFO
    }
    default {
        Write-Host "Opción inválida. Usando SOLO por defecto..." -ForegroundColor Yellow
        celery -A config worker -P solo -Q training -n worker-training@$env:COMPUTERNAME -l INFO
    }
}
