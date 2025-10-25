# Sistema de Ranking Adaptativo - Resumen Completo

Documentación completa del sistema de ranking adaptativo con comandos de gestión y dashboard web.

## Estructura del Sistema

```
apps/
├── ranking_adaptive/              # Sistema de ranking adaptativo
│   ├── models.py                  # Modelos de datos
│   ├── tasks.py                   # Tareas de entrenamiento (Celery)
│   ├── utils.py                   # Utilidades y dataset builder
│   └── management/commands/       # Comandos de gestión
│       ├── train_ranking_weights.py
│       ├── list_ranking_versions.py
│       ├── evaluate_ranking_model.py
│       ├── export_training_data.py
│       ├── run_training_cycle.py
│       ├── activate_ranking_weights.py
│       ├── activate_prev_weights.py
│       └── report_adaptive_metrics.py
│
└── ranking_dashboard/             # Dashboard web
    ├── views.py                   # Vistas con validación staff
    ├── urls.py                    # Rutas
    ├── templates/ranking_dashboard/
    │   ├── base.html
    │   ├── home.html
    │   ├── train.html
    │   ├── versions.html
    │   ├── evaluate.html
    │   ├── cycle.html
    │   ├── cycle_result.html
    │   └── export.html
    ├── README.md
    └── SETUP.md
```

## Componentes Creados

### 1. Comandos de Gestión (8 comandos)

#### Nuevos Comandos:

1. **`train_ranking_weights`** - Entrena nuevos pesos
   - Parámetros: days, lr, steps, l2, clip-rel, nonneg-idx
   - Output: Versión nueva (ej: `w_20251025_143022`)

2. **`list_ranking_versions`** - Lista versiones
   - Parámetros: limit, verbose
   - Muestra estado activo/inactivo

3. **`evaluate_ranking_model`** - Evalúa versión
   - Parámetros: version, days, compare
   - Métricas: dataset, feedback, pesos, comparación

4. **`export_training_data`** - Exporta datos
   - Parámetros: output, days, include-raw
   - Formato: JSON

5. **`run_training_cycle`** - Pipeline completo
   - Parámetros: days, eval-days, auto-activate, export
   - Ejecuta: listar → entrenar → evaluar → activar

#### Comandos Existentes:

6. **`activate_ranking_weights`** - Activa versión
7. **`activate_prev_weights`** - Rollback rápido
8. **`report_adaptive_metrics`** - Métricas de rendimiento

### 2. Dashboard Web

#### Características:
- Validación de usuario staff (`@login_required` + `@user_passes_test(is_staff)`)
- Interfaz con Tailwind CSS
- Color primary: `#023f66`
- Sin emojis decorativos

#### Páginas:

1. **Dashboard Principal** (`/ranking/`)
   - Vista general del sistema
   - Versión activa
   - Acciones rápidas
   - Tabla de versiones recientes

2. **Entrenar** (`/ranking/train/`)
   - Formulario con parámetros configurables
   - Ejecuta entrenamiento

3. **Versiones** (`/ranking/versions/`)
   - Lista completa de versiones
   - Acciones: evaluar, activar
   - Botón de rollback

4. **Evaluación** (`/ranking/versions/<version>/evaluate/`)
   - Métricas detalladas
   - Comparación con versión anterior
   - Opción de activar

5. **Ciclo Completo** (`/ranking/cycle/`)
   - Pipeline automatizado
   - Auto-activación opcional

6. **Exportar** (`/ranking/export/`)
   - Exportar datos a JSON

## Flujos de Trabajo

### A. Desde CLI (Comandos)

#### Manual:
```bash
# 1. Listar versiones
python manage.py list_ranking_versions --limit 5

# 2. Entrenar
python manage.py train_ranking_weights --days 30 --lr 0.005 --steps 800

# 3. Evaluar
python manage.py evaluate_ranking_model --version w_20251025_143022 --compare

# 4. Activar
python manage.py activate_ranking_weights w_20251025_143022

# 5. Monitorear
python manage.py report_adaptive_metrics --hours 24
```

#### Automatizado:
```bash
# Ciclo completo con auto-activación
python manage.py run_training_cycle --days 30 --auto-activate

# Ciclo completo sin auto-activación
python manage.py run_training_cycle --days 30 --export
```

#### Rollback:
```bash
python manage.py activate_prev_weights
```

### B. Desde Dashboard Web

#### Manual:
1. Acceder a `http://localhost:8000/ranking/`
2. Click "Entrenar Nueva Versión"
3. Configurar parámetros
4. Entrenar
5. Ir a "Gestionar Versiones"
6. Click "Evaluar" en nueva versión
7. Revisar métricas
8. Click "Activar" si es satisfactoria

#### Automatizado:
1. Acceder a `http://localhost:8000/ranking/`
2. Click "Ciclo Completo"
3. Marcar "Activar automáticamente" (opcional)
4. Ejecutar
5. Revisar output

#### Rollback:
1. Ir a "Gestionar Versiones"
2. Click "Rollback a Anterior"
3. Confirmar

## Algoritmo de Entrenamiento

### Pairwise Learning

1. **Construcción de pares**:
   - Identifica chunks con feedback positivo y negativo por consulta
   - Genera pares (útil, no_útil)
   - Aplica IPS (Inverse Propensity Score) por posición

2. **Optimización**:
   - Función objetivo: Logistic loss + L2 regularización
   - Gradiente descendente
   - Constraints: clip relativo y no-negatividad

3. **Regularización**:
   - L2 hacia pesos previos (evita cambios bruscos)
   - Clip relativo (limita desviación ±X%)
   - Non-negativity en índices específicos

## Modelos de Datos

### RankingWeights
- `version`: str (único, timestamp)
- `weights`: float[] (vector de pesos)
- `is_active`: bool (solo una activa)
- `created_at`: datetime
- `notes`: str (metadatos)

### RankingDecision
- `query_id`: int
- `hit_id`: int (chunk_id)
- `model_version`: str
- `score_ce`: float
- `rank_before`: int
- `rank_after`: int
- `shown_pos`: int
- `signals`: float[]
- `signal_names`: str[]
- `ts`: datetime

### Feedback (en app search)
- `hit`: ForeignKey(SearchHit)
- `label`: str ('useful' | 'not_useful')
- `created_at`: datetime

## Seguridad

### Dashboard
- `@login_required`: Requiere autenticación
- `@user_passes_test(is_staff)`: Solo usuarios staff
- CSRF protection habilitado
- Confirmaciones en acciones críticas

### Comandos
- Validación de parámetros
- Transacciones atómicas
- Manejo de errores

## Configuración

### Settings
```python
INSTALLED_APPS = [
    # ...
    "apps.ranking_adaptive",
    "apps.ranking_dashboard",
]
```

### URLs
```python
urlpatterns = [
    # ...
    path("ranking/", include("apps.ranking_dashboard.urls")),
]
```

### Environment
```
BRAND_PRIMARY_COLOR=#023f66
```

## Métricas Clave

1. **Útil@top10**: Proporción de items útiles en top-10
   - Target: > 0.7

2. **Engagement rate**: Proporción de items con feedback
   - Target: > 0.3

3. **Pares de entrenamiento**: Cantidad de datos
   - Target: > 500 pares

## Requisitos Previos

Para que el sistema funcione:

1. **Feedback de usuarios**: Datos de útil/no útil
2. **Decisiones registradas**: RankingDecision con señales
3. **Ventana temporal**: Al menos algunos días de datos

### Verificar Datos
```python
from apps.search.models import Feedback
from apps.ranking_adaptive.models import RankingDecision

print(f"Feedbacks: {Feedback.objects.filter(hit__isnull=False).count()}")
print(f"Decisiones: {RankingDecision.objects.count()}")
```

## Acceso Rápido

### Dashboard
- URL: `http://localhost:8000/ranking/`
- Requiere: Usuario staff

### Crear Usuario Staff
```bash
python manage.py createsuperuser
```

O convertir existente:
```python
from django.contrib.auth import get_user_model
User = get_user_model()
user = User.objects.get(email='email@example.com')
user.is_staff = True
user.save()
```

## Troubleshooting

### "No hay datos suficientes para entrenar"
- Acumula más feedback de usuarios
- Reduce ventana temporal (ej: 7 días)
- Verifica que hay feedback registrado

### Error 403 en Dashboard
- Usuario no tiene `is_staff=True`
- Otorga permisos de staff al usuario

### Comandos no funcionan
- Verifica que los modelos existen
- Revisa logs de Django
- Ejecuta comandos con `--help` para ver opciones

## Recomendaciones

### Frecuencia de Entrenamiento
- **Desarrollo**: Bajo demanda
- **Producción**: Semanal o quincenal

### Ventana de Datos
- **Recomendado**: 30 días
- Balance entre recencia y volumen

### Evaluación
- Siempre evaluar antes de activar
- Comparar con versión anterior
- Monitorear métricas post-activación

### Rollback
- Mantener al menos 5 versiones históricas
- Rollback disponible en 1 click
- Monitorear después de activar nueva versión

## Próximos Pasos

1. **Setup inicial**:
   - Crear usuario staff
   - Verificar datos disponibles
   - Acceder al dashboard

2. **Primera ejecución**:
   - Entrenar primera versión
   - Evaluar métricas
   - Activar si es satisfactoria

3. **Operación continua**:
   - Monitorear métricas
   - Re-entrenar semanalmente
   - Ajustar hiperparámetros según resultados

4. **Optimización**:
   - Analizar datos exportados
   - Ajustar señales si es necesario
   - Experimentar con parámetros

## Documentación Adicional

- **Comandos**: `apps/ranking_adaptive/management/commands/` (ver cada archivo)
- **Dashboard**: `apps/ranking_dashboard/README.md`
- **Setup**: `apps/ranking_dashboard/SETUP.md`

---

**Sistema completo y funcional**
- 8 comandos de gestión
- Dashboard web con 6 páginas
- Validación de seguridad
- Documentación completa

**Versión**: 1.0.0
**Fecha**: 2025-10-25
