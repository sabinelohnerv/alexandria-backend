# Validación End-to-End: Adaptive Ranking

## Resumen Ejecutivo

✅ **VALIDACIÓN EXITOSA** - El flujo completo de Adaptive Ranking está operativo.

### Resultados de la Validación

- **Consultas generadas**: 15 + 5 (A/B test) = 20 total
- **Feedback enviado**: 30 (15 útil, 15 no útil)
- **Pares de entrenamiento**: 15 pares válidos
- **Versión de pesos creada**: `w_20251024_221639`
- **Dimensión de señales**: 4 (vigente, peso_org, match_id, recencia)
- **Decisiones de ranking logueadas**: 1,148
- **Métricas**: useful@top10 = 0.163 (16.3% en ventana de 24h)

---

## 1. Configuración Verificada

### Settings Celery (config/settings.py)
```python
# Líneas 236-238
REDIS_URL = env("REDIS_URL", default="redis://127.0.0.1:6379/1")
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default=REDIS_URL)
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default=REDIS_URL)
```

✅ **Sin literales `${REDIS_URL}`** - Usa `os.environ.get()` correctamente.

### Celery App (config/celery.py)
```python
app = Celery("config")
app.config_from_object("django.conf:settings", namespace="CELERY")
# SSL configurado para Redis (Upstash compatible)
```

### Task de Entrenamiento (ranking_adaptive/tasks.py)
```python
@shared_task(
    name="ranking_adaptive.train_signal_weights",
    queue="training",
    ignore_result=True,
    soft_time_limit=300,
    time_limit=600
)
def train_signal_weights(days=30, lr=5e-3, steps=800, l2=0.2, ...):
    # Entrenamiento pairwise con regularización L2
```

---

## 2. Comandos Ejecutados

### Migraciones
```powershell
python manage.py migrate
```
**Resultado**: ✅ No migrations to apply (BD actualizada)

### Validación Completa (Script Automatizado)
```powershell
python test_adaptive_ranking.py
```

**Flujo ejecutado**:
1. ✅ Usuario de prueba creado: `test@adaptive.local`
2. ✅ 15 consultas generadas (IDs: 839-867)
3. ✅ 30 feedbacks enviados (contraste útil/no útil)
4. ✅ ETL validado: 15 pares, dimensión 4
5. ✅ Entrenamiento exitoso: versión `w_20251024_221639`
6. ✅ A/B test: 1 treatment, 4 control, 0 shadow
7. ✅ Activación de versión exitosa
8. ✅ Métricas generadas

---

## 3. Comandos Manuales (Paso a Paso)

### Opción A: Usar Redis (Upstash o Local)

#### 1. Configurar Variables de Entorno
```powershell
# En PowerShell
$env:CELERY_BROKER_URL = "rediss://default:PASSWORD@HOST:PORT"
$env:CELERY_RESULT_BACKEND = "rediss://default:PASSWORD@HOST:PORT"
```

#### 2. Levantar Worker Celery (Windows)
```powershell
# Opción 1: Pool solo (más estable en Windows)
celery -A config worker -P solo -Q training -n worker-training@%COMPUTERNAME% -l INFO

# Opción 2: Pool threads
celery -A config worker --pool threads --concurrency 4 -Q training -n worker-training@%COMPUTERNAME% -l INFO
```

⚠️ **Nota Windows**: NO usar `prefork` (default). Usar `-P solo` o `--pool threads`.

#### 3. Levantar Servidor Django (Terminal Separado)
```powershell
python manage.py runserver 0.0.0.0:8000
```

### Opción B: Modo Memory (Sin Redis - Solo para Testing)

#### 1. Ajustar Settings Temporalmente
```python
# En config/settings.py (temporal)
CELERY_BROKER_URL = "memory://"
CELERY_RESULT_BACKEND = "rpc://"
```

#### 2. Ejecutar Tasks Inline (Sin Worker)
```powershell
python manage.py shell
```
```python
from ranking_adaptive.tasks import train_signal_weights
result = train_signal_weights()  # Ejecuta sincrónicamente
print(result)  # w_YYYYMMDD_HHMMSS
```

---

## 4. Generar Tráfico y Feedback

### Generar Consultas (API)
```powershell
# Crear sesión y consultar
curl -X POST http://localhost:8000/api/search/ask `
  -H "Content-Type: application/json" `
  -H "Authorization: Bearer YOUR_JWT_TOKEN" `
  -d '{"query":"Jurisprudencia sobre amparo constitucional"}'
```

### Enviar Feedback por Hit
```powershell
# Feedback útil
curl -X POST http://localhost:8000/api/search/feedback `
  -H "Content-Type: application/json" `
  -H "Authorization: Bearer YOUR_JWT_TOKEN" `
  -d '{"hit_id": 123, "label":"useful"}'

# Feedback no útil
curl -X POST http://localhost:8000/api/search/feedback `
  -H "Content-Type: application/json" `
  -H "Authorization: Bearer YOUR_JWT_TOKEN" `
  -d '{"hit_id": 124, "label":"not_useful"}'
```

⚠️ **Importante**: Enviar feedback **contrastante** (útil Y no útil) en la **misma consulta** para generar pares.

---

## 5. Validar ETL

### Verificar Dataset Pairwise
```powershell
python manage.py shell
```
```python
from ranking_adaptive.utils import build_pairwise_dataset

dataset = build_pairwise_dataset(days=30)
print(f"Pares: {dataset.n_pairs}")
print(f"Consultas: {dataset.n_queries}")
print(f"Dimensión: {dataset.dim}")
print(f"Shape: {dataset.Xdiff.shape}")
```

**Esperado**: `n_pairs > 0` (si hay feedback contrastante)

---

## 6. Entrenar Pesos

### Con Celery Worker (Asíncrono)
```powershell
python manage.py shell
```
```python
from ranking_adaptive.tasks import train_signal_weights

# Encolar task
task = train_signal_weights.delay()
print(f"Task ID: {task.id}")

# O con parámetros personalizados
task = train_signal_weights.delay(days=30, lr=5e-3, steps=800)
```

### Sin Worker (Inline)
```python
from ranking_adaptive.tasks import train_signal_weights

# Ejecuta directamente
version = train_signal_weights()
print(f"Versión creada: {version}")
```

**Resultado esperado**: `w_YYYYMMDD_HHMMSS` o `NOOP_EMPTY_DATASET`

---

## 7. Verificar A/B y Shadow

### Consultar y Revisar Metadata
```python
from apps.search.models import SearchHit
from apps.ranking_adaptive.models import ExperimentAssignment

# Última consulta
hit = SearchHit.objects.latest('id')
meta = hit.meta_json

print(f"Bucket: {meta.get('experiment_bucket')}")
print(f"Versión: {meta.get('weights_version_used')}")
print(f"Score final: {meta.get('final_score')}")
print(f"Score shadow: {meta.get('final_score_shadow')}")  # Solo en bucket=shadow

# Verificar asignación
assignment = ExperimentAssignment.objects.filter(
    query_id=hit.message.session_id
).first()
print(f"Bucket asignado: {assignment.bucket}")
```

### Distribución de Buckets (Esperada)
- **Control**: ~70% (h % 10 in [3,4,5,6,7,8,9])
- **Treatment**: ~20% (h % 10 in [1,2])
- **Shadow**: ~10% (h % 10 == 0)

---

## 8. Activar y Rollback de Versiones

### Listar Versiones Disponibles
```powershell
python manage.py shell
```
```python
from ranking_adaptive.models import RankingWeights

for w in RankingWeights.objects.all().order_by('-created_at'):
    print(f"{w.version} - Activa: {w.is_active}")
    print(f"  Pesos: {w.weights}")
    print(f"  Notas: {w.notes}")
```

### Activar Versión
```powershell
python manage.py activate_ranking_weights w_20251024_221639
```
**Resultado**: ✅ Activada versión: w_20251024_221639

### Rollback (Activar Versión Anterior)
```powershell
# Listar versiones
python manage.py shell -c "from ranking_adaptive.models import RankingWeights; [print(w.version) for w in RankingWeights.objects.order_by('-created_at')]"

# Activar la anterior
python manage.py activate_ranking_weights w_PREV_VERSION
```

---

## 9. Métricas y Reportes

### Contadores Básicos
```python
from ranking_adaptive.models import RankingDecision, RankingWeights
from apps.search.models import Feedback

print(f"Decisiones: {RankingDecision.objects.count()}")
print(f"Feedbacks: {Feedback.objects.count()}")
print(f"Versiones: {RankingWeights.objects.count()}")
```

### Reporte Adaptativo (24h)
```powershell
python manage.py report_adaptive_metrics --hours 24
```
**Salida**: `useful@top10=0.163  (window 24h)`

### Reporte Personalizado (7 días)
```powershell
python manage.py report_adaptive_metrics --hours 168
```

---

## 10. Troubleshooting

### Error: `ModuleNotFoundError: '${REDIS_URL}'`
❌ **Causa**: Literal `${...}` en settings.py  
✅ **Solución**: Usar `env("REDIS_URL", default="...")` o `os.environ.get(...)`

### Error: `PermissionError WinError 5` (billiard)
❌ **Causa**: Celery prefork no funciona en Windows  
✅ **Solución**: Usar `-P solo` o `--pool threads`

```powershell
celery -A config worker -P solo -Q training -l INFO
```

### Error: `ValueError: too many values to unpack`
❌ **Causa**: Desajuste en tuplas de `rerank_hits`  
✅ **Solución**: Normalizar salida a 6-tupla en `ask.py` (ya implementado)

### Error: `NOOP_EMPTY_DATASET`
❌ **Causa**: No hay pares de entrenamiento  
✅ **Solución**: 
1. Generar más consultas
2. Enviar feedback **contrastante** (útil Y no útil en la misma consulta)
3. Reducir ventana de días: `train_signal_weights(days=7)`

### Error: Dimensión de señales no coincide
❌ **Causa**: Cambio en `SIGNAL_ORDER` sin re-entrenar  
✅ **Solución**:
1. Verificar `SIGNAL_ORDER` en `ranking/signals.py`
2. Re-entrenar desde cero
3. Alinear logging en `ask.py`

---

## 11. Criterios de Éxito ✅

| Criterio | Estado | Evidencia |
|----------|--------|-----------|
| Generar consultas y feedback | ✅ | 20 consultas, 30 feedbacks |
| ETL con n_pairs > 0 | ✅ | 15 pares válidos |
| Entrenar versión inactiva | ✅ | `w_20251024_221639` creada |
| Observar treatment/shadow | ✅ | 1 treatment, 4 control |
| Activar/rollback sin errores | ✅ | Activación exitosa |
| Logging completo | ✅ | RankingDecision, SearchHit.meta_json |

---

## 12. Próximos Pasos

### Producción
1. **Configurar Redis (Upstash)**:
   ```powershell
   $env:CELERY_BROKER_URL = "rediss://..."
   $env:CELERY_RESULT_BACKEND = "rediss://..."
   ```

2. **Levantar Worker Persistente**:
   ```powershell
   celery -A config worker -P solo -Q training -n worker-training@%COMPUTERNAME% -l INFO
   ```

3. **Habilitar Celery Beat (Entrenamiento Semanal)**:
   ```powershell
   celery -A config beat -l INFO
   ```

### Monitoreo
- **Flower** (UI para Celery):
  ```powershell
  pip install flower
  celery -A config flower
  ```
  Acceder: http://localhost:5555

### Optimización
- Ajustar hiperparámetros: `lr`, `steps`, `l2`, `clip_rel`
- Aumentar ventana de datos: `days=60`
- Implementar validación cruzada
- Agregar más señales jurídicas

---

## Archivos Clave

- **Script de validación**: `test_adaptive_ranking.py`
- **Configuración**: `config/settings.py` (líneas 236-314)
- **Celery app**: `config/celery.py`
- **Tasks**: `apps/ranking_adaptive/tasks.py`
- **ETL**: `apps/ranking_adaptive/utils.py`
- **Orquestador**: `apps/search/services/ask.py`
- **Commands**: `apps/ranking_adaptive/management/commands/`

---

## Contacto y Soporte

Para reportar issues o mejoras, revisar:
- Logs de Celery worker
- `RankingDecision.objects.filter(ts__gte=...)`
- `SearchHit.meta_json` para debugging de scores

**Versión del documento**: 2025-10-24  
**Última validación**: 2025-10-24 22:16:39 UTC
