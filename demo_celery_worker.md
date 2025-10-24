# Demo: Celery Worker en Windows

## Opción 1: Modo Memory (Sin Redis - Testing Rápido)

### Paso 1: Ajustar Settings Temporalmente
Edita `config/settings.py` y cambia temporalmente:

```python
# Líneas 237-238 (temporal para testing)
CELERY_BROKER_URL = "memory://"
CELERY_RESULT_BACKEND = "rpc://"
```

### Paso 2: Ejecutar Task Inline (Sin Worker)
```powershell
python manage.py shell
```

```python
from ranking_adaptive.tasks import train_signal_weights

# Ejecuta sincrónicamente (sin worker)
result = train_signal_weights()
print(f"Versión creada: {result}")
```

**Ventajas**: 
- ✅ No requiere Redis
- ✅ No requiere worker separado
- ✅ Ideal para testing local

**Desventajas**:
- ❌ No es asíncrono
- ❌ No es escalable
- ❌ No sirve para producción

---

## Opción 2: Redis Local (Docker)

### Paso 1: Levantar Redis con Docker
```powershell
docker run -d -p 6379:6379 --name redis-local redis:7-alpine
```

### Paso 2: Configurar Settings
En `config/settings.py`:
```python
CELERY_BROKER_URL = "redis://localhost:6379/1"
CELERY_RESULT_BACKEND = "redis://localhost:6379/1"
```

### Paso 3: Levantar Worker (Terminal 1)
```powershell
# Pool solo (recomendado para Windows)
celery -A config worker -P solo -Q training -n worker-training@%COMPUTERNAME% -l INFO
```

O con el script PowerShell:
```powershell
.\run_celery_worker.ps1
# Selecciona opción 1 (Solo)
```

### Paso 4: Encolar Task (Terminal 2)
```powershell
python manage.py shell
```

```python
from ranking_adaptive.tasks import train_signal_weights

# Encola el task (asíncrono)
task = train_signal_weights.delay()
print(f"Task ID: {task.id}")

# Verificar estado (opcional)
print(f"Estado: {task.state}")
```

**Salida esperada en Terminal 1 (worker)**:
```
[2025-10-24 22:16:39,123: INFO/MainProcess] Task ranking_adaptive.train_signal_weights[abc-123] received
[2025-10-24 22:16:40,456: INFO/MainProcess] Task ranking_adaptive.train_signal_weights[abc-123] succeeded in 1.2s: 'w_20251024_221639'
```

---

## Opción 3: Redis Upstash (Producción)

### Paso 1: Crear Cuenta en Upstash
1. Ir a https://upstash.com/
2. Crear base de datos Redis
3. Copiar URL de conexión (formato: `rediss://default:PASSWORD@HOST:PORT`)

### Paso 2: Configurar Variables de Entorno
```powershell
# En PowerShell (sesión actual)
$env:CELERY_BROKER_URL = "rediss://default:YOUR_PASSWORD@YOUR_HOST:PORT"
$env:CELERY_RESULT_BACKEND = "rediss://default:YOUR_PASSWORD@YOUR_HOST:PORT"
```

O crear archivo `.env`:
```env
CELERY_BROKER_URL=rediss://default:YOUR_PASSWORD@YOUR_HOST:PORT
CELERY_RESULT_BACKEND=rediss://default:YOUR_PASSWORD@YOUR_HOST:PORT
```

### Paso 3: Levantar Worker
```powershell
celery -A config worker -P solo -Q training -n worker-training@%COMPUTERNAME% -l INFO
```

### Paso 4: Verificar Conexión
Si ves este mensaje, la conexión es exitosa:
```
[2025-10-24 22:16:39,123: INFO/MainProcess] Connected to rediss://...
[2025-10-24 22:16:39,456: INFO/MainProcess] mingle: searching for neighbors
[2025-10-24 22:16:40,789: INFO/MainProcess] mingle: all alone
[2025-10-24 22:16:40,890: INFO/MainProcess] celery@worker-training ready.
```

---

## Opción 4: Celery Beat (Entrenamiento Programado)

### Configuración en settings.py
Ya está configurado (líneas 308-314):
```python
CELERY_BEAT_SCHEDULE = {
    "train-signal-weights-weekly": {
        "task": "ranking_adaptive.tasks.train_signal_weights",
        "schedule": crontab(hour=3, minute=0, day_of_week="sun"),  # Domingos 03:00
        "args": (),
    },
}
```

### Levantar Beat (Terminal 3)
```powershell
celery -A config beat -l INFO
```

**Salida esperada**:
```
[2025-10-24 22:16:39,123: INFO/MainProcess] beat: Starting...
[2025-10-24 22:16:39,456: INFO/MainProcess] Scheduler: Sending due task train-signal-weights-weekly (ranking_adaptive.tasks.train_signal_weights)
```

---

## Troubleshooting Windows

### Error: `PermissionError: [WinError 5]`
**Causa**: Celery prefork no funciona en Windows

**Solución**: Usar `-P solo` o `--pool threads`
```powershell
celery -A config worker -P solo -Q training -l INFO
```

### Error: `billiard.exceptions.TimeLimitExceeded`
**Causa**: Task excede time_limit

**Solución**: Aumentar límite en task:
```python
@shared_task(soft_time_limit=600, time_limit=1200)  # 10 min soft, 20 min hard
```

### Error: `ModuleNotFoundError: No module named 'celery'`
**Solución**: Instalar Celery
```powershell
pip install celery[redis]
```

### Error: `ConnectionError: Error 10061 connecting to localhost:6379`
**Causa**: Redis no está corriendo

**Solución**: Levantar Redis (Docker o Upstash)
```powershell
docker run -d -p 6379:6379 redis:7-alpine
```

---

## Comandos de Monitoreo

### Ver tasks activos
```powershell
celery -A config inspect active
```

### Ver workers registrados
```powershell
celery -A config inspect registered
```

### Ver estadísticas
```powershell
celery -A config inspect stats
```

### Purgar cola
```powershell
celery -A config purge
```

---

## Flower (UI de Monitoreo)

### Instalación
```powershell
pip install flower
```

### Levantar Flower
```powershell
celery -A config flower
```

### Acceder
Abrir navegador: http://localhost:5555

**Funcionalidades**:
- Ver tasks en tiempo real
- Ver workers activos
- Ver estadísticas de rendimiento
- Reintentar tasks fallidos

---

## Resumen de Comandos

| Comando | Descripción |
|---------|-------------|
| `celery -A config worker -P solo -Q training -l INFO` | Levantar worker (Windows) |
| `celery -A config beat -l INFO` | Levantar scheduler |
| `celery -A config flower` | Levantar UI de monitoreo |
| `celery -A config inspect active` | Ver tasks activos |
| `celery -A config purge` | Limpiar cola |
| `python manage.py shell -c "..."` | Ejecutar task inline |

---

## Ejemplo Completo (3 Terminales)

### Terminal 1: Worker
```powershell
cd d:\django_docker_db
celery -A config worker -P solo -Q training -n worker-training@%COMPUTERNAME% -l INFO
```

### Terminal 2: Beat (opcional)
```powershell
cd d:\django_docker_db
celery -A config beat -l INFO
```

### Terminal 3: Encolar Task
```powershell
cd d:\django_docker_db
python manage.py shell
```
```python
from ranking_adaptive.tasks import train_signal_weights
task = train_signal_weights.delay()
print(f"Task encolado: {task.id}")
```

**Resultado**: El worker (Terminal 1) procesará el task y mostrará el resultado.

---

## Recomendación Final

Para **desarrollo local en Windows**:
- ✅ Usar `-P solo` (más estable)
- ✅ Usar Redis local (Docker) o Upstash
- ✅ Levantar worker en terminal separado
- ✅ Usar Flower para monitoreo visual

Para **producción**:
- ✅ Usar Upstash Redis (managed)
- ✅ Usar `-P solo` en Windows Server
- ✅ Configurar supervisor/systemd para auto-restart
- ✅ Habilitar Celery Beat para tareas programadas
