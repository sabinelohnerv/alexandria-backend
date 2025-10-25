# Comandos de Gestión - Ranking Adaptativo

Este directorio contiene comandos de Django para gestionar el ciclo completo de entrenamiento, evaluación y despliegue del sistema de ranking adaptativo.

## 📋 Índice

- [Comandos Disponibles](#comandos-disponibles)
- [Flujo de Trabajo Completo](#flujo-de-trabajo-completo)
- [Ejemplos de Uso](#ejemplos-de-uso)
- [Arquitectura del Sistema](#arquitectura-del-sistema)
- [Troubleshooting](#troubleshooting)

---

## 🛠️ Comandos Disponibles

### 1. `train_ranking_weights`
**Propósito:** Entrena nuevos pesos de señales usando feedback histórico mediante aprendizaje pairwise.

**Uso:**
```bash
python manage.py train_ranking_weights [opciones]
```

**Opciones:**
- `--days N` - Ventana de días de feedback histórico (default: 30)
- `--lr FLOAT` - Learning rate (default: 0.005)
- `--steps N` - Número de pasos de optimización (default: 800)
- `--l2 FLOAT` - Regularización L2 hacia pesos previos (default: 0.2)
- `--clip-rel FLOAT` - Clip relativo: ±X% del peso previo (default: 0.5)
- `--nonneg-idx STR` - Índices de señales no-negativas (default: "0,1")

**Ejemplo:**
```bash
python manage.py train_ranking_weights --days 30 --lr 0.005 --steps 800
```

**Output:**
- Crea una nueva versión de pesos con nombre `w_YYYYMMDD_HHMMSS`
- La versión se guarda en estado `is_active=False` (requiere activación manual)

---

### 2. `list_ranking_versions`
**Propósito:** Lista todas las versiones de pesos almacenadas con su estado y metadatos.

**Uso:**
```bash
python manage.py list_ranking_versions [opciones]
```

**Opciones:**
- `--limit N` - Número máximo de versiones a mostrar (default: 20)
- `--verbose` - Muestra información detallada incluyendo pesos

**Ejemplo:**
```bash
python manage.py list_ranking_versions --limit 10 --verbose
```

**Output:**
```
=== Versiones de Pesos de Ranking ===

🟢 [1] w_20251025_143022
    Estado: ACTIVA
    Creada: 2025-10-25 14:30:22
    Dimensión: 5 señales
    Pesos: [0.1234, 0.5678, -0.0234, 0.8901, 0.2345]
    Notas: pairwise training: days=30 pairs=1250 l2=0.2 steps=800

⚪ [2] w_20251024_120015
    Estado: inactiva
    ...
```

---

### 3. `evaluate_ranking_model`
**Propósito:** Evalúa el rendimiento de una versión de pesos específica.

**Uso:**
```bash
python manage.py evaluate_ranking_model [opciones]
```

**Opciones:**
- `--version STR` - Versión específica a evaluar (si no se especifica, usa la activa)
- `--days N` - Ventana de evaluación en días (default: 7)
- `--compare` - Compara con la versión anterior

**Ejemplo:**
```bash
python manage.py evaluate_ranking_model --version w_20251025_143022 --days 7 --compare
```

**Métricas evaluadas:**
1. **Dataset de Entrenamiento**
   - Consultas procesadas
   - Pares generados
   - Dimensión de señales

2. **Métricas de Feedback**
   - Útil@top10: Tasa de feedback positivo en top-10
   - No útil@top10: Tasa de feedback negativo
   - Engagement rate: Tasa de interacción total

3. **Análisis de Pesos**
   - L2 norm
   - Distribución de pesos (max, min, positivos, negativos)

4. **Comparación con Versión Anterior** (si `--compare`)
   - Diferencia L2 entre versiones
   - Cambios relativos por señal

---

### 4. `activate_ranking_weights`
**Propósito:** Activa una versión específica de pesos para uso en producción.

**Uso:**
```bash
python manage.py activate_ranking_weights <version>
```

**Ejemplo:**
```bash
python manage.py activate_ranking_weights w_20251025_143022
```

**Comportamiento:**
- Desactiva todas las versiones actuales (`is_active=False`)
- Activa la versión especificada (`is_active=True`)
- Operación atómica (transacción)

---

### 5. `activate_prev_weights`
**Propósito:** Rollback rápido a la versión anterior (útil si la nueva versión tiene problemas).

**Uso:**
```bash
python manage.py activate_prev_weights
```

**Comportamiento:**
- Desactiva la versión más reciente
- Activa la segunda versión más reciente

---

### 6. `report_adaptive_metrics`
**Propósito:** Reporta métricas de rendimiento del sistema en una ventana temporal.

**Uso:**
```bash
python manage.py report_adaptive_metrics [opciones]
```

**Opciones:**
- `--hours N` - Ventana temporal en horas (default: 24)

**Ejemplo:**
```bash
python manage.py report_adaptive_metrics --hours 24
```

**Output:**
```
useful@top10=0.723  (window 24h)
```

---

### 7. `export_training_data`
**Propósito:** Exporta datos de entrenamiento y métricas para análisis offline.

**Uso:**
```bash
python manage.py export_training_data [opciones]
```

**Opciones:**
- `--output FILE` - Archivo de salida (default: training_data_export.json)
- `--days N` - Ventana de datos en días (default: 30)
- `--include-raw` - Incluye decisiones y feedback raw (limitado a 1000 items)

**Ejemplo:**
```bash
python manage.py export_training_data --output export_20251025.json --days 30 --include-raw
```

**Contenido del export:**
```json
{
  "metadata": {
    "export_timestamp": "2025-10-25T14:30:22Z",
    "window_days": 30
  },
  "dataset": {
    "n_queries": 450,
    "n_pairs": 1250,
    "dimension": 5
  },
  "versions": [...],
  "statistics": {
    "decisions": {...},
    "feedback": {...}
  },
  "raw_decisions": [...],
  "raw_feedback": [...]
}
```

---

### 8. `run_training_cycle` ⭐
**Propósito:** Ejecuta el ciclo completo de entrenamiento de forma automatizada.

**Uso:**
```bash
python manage.py run_training_cycle [opciones]
```

**Opciones:**
- `--days N` - Ventana de datos para entrenamiento (default: 30)
- `--eval-days N` - Ventana de evaluación (default: 7)
- `--auto-activate` - Activa automáticamente la nueva versión
- `--export` - Exporta datos al final
- `--lr FLOAT` - Learning rate (default: 0.005)
- `--steps N` - Pasos de optimización (default: 800)

**Ejemplo:**
```bash
python manage.py run_training_cycle --days 30 --eval-days 7 --auto-activate --export
```

**Pipeline ejecutado:**
1. Lista versiones actuales
2. Entrena nueva versión
3. Evalúa nueva versión (con comparación)
4. Activa nueva versión (si `--auto-activate`)
5. Exporta datos (si `--export`)

---

## 🔄 Flujo de Trabajo Completo

### Opción A: Pipeline Automatizado (Recomendado)

```bash
# Ciclo completo con activación automática
python manage.py run_training_cycle --days 30 --auto-activate

# Ciclo completo sin activación (revisión manual)
python manage.py run_training_cycle --days 30
```

### Opción B: Paso a Paso (Control Manual)

```bash
# 1. Ver versiones actuales
python manage.py list_ranking_versions --limit 5

# 2. Entrenar nueva versión
python manage.py train_ranking_weights --days 30 --lr 0.005 --steps 800

# 3. Evaluar nueva versión (asume w_20251025_143022)
python manage.py evaluate_ranking_model --version w_20251025_143022 --compare

# 4. Si la evaluación es satisfactoria, activar
python manage.py activate_ranking_weights w_20251025_143022

# 5. Monitorear métricas
python manage.py report_adaptive_metrics --hours 24

# 6. Si hay problemas, rollback
python manage.py activate_prev_weights
```

### Opción C: Entrenamiento Programado (Celery)

```python
# En tu código o celery beat
from apps.ranking_adaptive.tasks import train_signal_weights

# Entrenar cada semana
result = train_signal_weights.apply_async(
    kwargs={'days': 30, 'lr': 5e-3, 'steps': 800}
)
```

---

## 🏗️ Arquitectura del Sistema

### Modelos de Datos

```python
# RankingWeights: Versiones de pesos
- version: str (único, ej: "w_20251025_143022")
- weights: float[] (vector de pesos)
- is_active: bool (solo una versión activa)
- created_at: datetime
- notes: str (metadatos del entrenamiento)

# RankingDecision: Decisiones de ranking registradas
- query_id: int (ID de consulta/mensaje)
- hit_id: int (ID de chunk)
- model_version: str (versión de pesos usada)
- score_ce: float (score del cross-encoder)
- rank_before: int (ranking antes de reranking)
- rank_after: int (ranking después de reranking)
- shown_pos: int (posición mostrada al usuario)
- signals: float[] (vector de señales normalizadas)
- signal_names: str[] (nombres de señales)
- ts: datetime

# Feedback: Feedback del usuario (en app search)
- hit: ForeignKey(SearchHit)
- label: str ('useful' | 'not_useful')
- created_at: datetime
```

### Algoritmo de Entrenamiento

El sistema usa **pairwise learning** con las siguientes características:

1. **Construcción de pares:**
   - Para cada consulta, identifica chunks con feedback positivo y negativo
   - Genera pares (chunk_útil, chunk_no_útil)
   - Aplica IPS (Inverse Propensity Score) por posición

2. **Optimización:**
   - Función objetivo: Logistic loss + regularización L2 hacia pesos previos
   - Gradiente descendente con learning rate configurable
   - Constraints: clip relativo ±X% y no-negatividad en índices específicos

3. **Regularización:**
   - L2 hacia pesos previos (evita cambios bruscos)
   - Clip relativo (limita desviación)
   - Non-negativity constraints (señales que deben ser positivas)

---

## 🔍 Troubleshooting

### Problema: "NOOP_EMPTY_DATASET"

**Causa:** No hay suficientes datos de feedback para entrenar.

**Solución:**
- Espera a acumular más feedback de usuarios
- Reduce `--days` si hay datos recientes pero no antiguos
- Verifica que el feedback se está registrando correctamente:
  ```bash
  python manage.py shell
  >>> from apps.search.models import Feedback
  >>> Feedback.objects.filter(hit__isnull=False).count()
  ```

### Problema: "No hay versión activa"

**Causa:** Ninguna versión de pesos está marcada como activa.

**Solución:**
```bash
python manage.py list_ranking_versions
python manage.py activate_ranking_weights <version_name>
```

### Problema: Métricas de evaluación bajas

**Causa:** La nueva versión no mejora el rendimiento.

**Solución:**
1. Revisa la comparación con versión anterior:
   ```bash
   python manage.py evaluate_ranking_model --version <version> --compare
   ```

2. Ajusta hiperparámetros:
   ```bash
   # Más conservador (más L2, menos learning rate)
   python manage.py train_ranking_weights --l2 0.5 --lr 0.001
   
   # Más datos
   python manage.py train_ranking_weights --days 60
   ```

3. Rollback si es necesario:
   ```bash
   python manage.py activate_prev_weights
   ```

### Problema: Entrenamiento muy lento

**Causa:** Demasiados pasos de optimización o datos.

**Solución:**
```bash
# Reduce pasos
python manage.py train_ranking_weights --steps 400

# Reduce ventana temporal
python manage.py train_ranking_weights --days 14
```

### Problema: Pesos se vuelven extremos

**Causa:** Learning rate muy alto o regularización muy baja.

**Solución:**
```bash
# Aumenta regularización y reduce LR
python manage.py train_ranking_weights --l2 0.5 --lr 0.001 --clip-rel 0.3
```

---

## 📊 Monitoreo en Producción

### Métricas Clave

1. **Útil@top10:** Proporción de items útiles en top-10
   - Target: > 0.7
   - Comando: `python manage.py report_adaptive_metrics --hours 24`

2. **Engagement rate:** Proporción de items con feedback
   - Target: > 0.3
   - Comando: `python manage.py evaluate_ranking_model --days 7`

3. **Pares de entrenamiento:** Cantidad de datos disponibles
   - Target: > 500 pares
   - Comando: `python manage.py export_training_data --days 30`

### Recomendaciones

- **Frecuencia de entrenamiento:** Semanal o quincenal
- **Ventana de datos:** 30 días (balance entre recencia y volumen)
- **Evaluación:** Siempre comparar con versión anterior antes de activar
- **Rollback:** Mantener al menos 5 versiones históricas

---

## 🚀 Integración con CI/CD

### Ejemplo: Entrenamiento Semanal Automatizado

```yaml
# .github/workflows/train_ranking.yml
name: Weekly Ranking Training

on:
  schedule:
    - cron: '0 2 * * 1'  # Lunes a las 2 AM
  workflow_dispatch:

jobs:
  train:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Train and Evaluate
        run: |
          python manage.py run_training_cycle --days 30 --eval-days 7 --export
      - name: Upload Results
        uses: actions/upload-artifact@v2
        with:
          name: training-results
          path: training_export_*.json
```

---

## 📝 Notas Adicionales

- Todos los comandos son **idempotentes** y seguros de ejecutar múltiples veces
- Las operaciones de activación son **atómicas** (transacciones)
- Los exports son útiles para **análisis offline** y **debugging**
- El sistema mantiene **historial completo** de versiones

---

## 🤝 Contribuciones

Para añadir nuevos comandos:

1. Crea archivo en `apps/ranking_adaptive/management/commands/`
2. Hereda de `BaseCommand`
3. Implementa `handle()` y `add_arguments()`
4. Documenta en este README

---

**Última actualización:** 2025-10-25
**Versión:** 1.0.0
