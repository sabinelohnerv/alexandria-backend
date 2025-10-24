# 🚀 Comandos Rápidos - Adaptive Ranking

## 📋 Validación Completa (Un Solo Comando)

```powershell
python test_adaptive_ranking.py
```

**Ejecuta**:
- ✅ Genera 15 consultas
- ✅ Envía 30 feedbacks (contraste)
- ✅ Valida ETL (15 pares)
- ✅ Entrena pesos
- ✅ Prueba A/B y shadow
- ✅ Activa versión
- ✅ Genera métricas

---

## 🔍 Verificar Estado del Sistema

```powershell
python check_status.py
```

**Muestra**:
- Contadores (RankingWeights, RankingDecision, Feedback)
- Versión activa y candidata
- Dataset pairwise (pares, dimensión)
- Últimas decisiones
- Distribución de buckets
- Feedback reciente

---

## 🎯 Comandos Esenciales

### 1. Validar ETL
```powershell
python manage.py shell -c "from ranking_adaptive.utils import build_pairwise_dataset; d=build_pairwise_dataset(); print(f'Pares: {d.n_pairs}, Dim: {d.dim}')"
```

### 2. Entrenar Pesos (Inline)
```powershell
python manage.py shell -c "from ranking_adaptive.tasks import train_signal_weights; print(train_signal_weights())"
```

### 3. Activar Versión
```powershell
python manage.py activate_ranking_weights w_20251024_221639
```

### 4. Ver Métricas
```powershell
python manage.py report_adaptive_metrics --hours 24
```

### 5. Listar Versiones
```powershell
python manage.py shell -c "from ranking_adaptive.models import RankingWeights; [print(f'{w.version} - Activa: {w.is_active}') for w in RankingWeights.objects.order_by('-created_at')]"
```

---

## 🔧 Celery Worker (Windows)

### Opción 1: Pool Solo (Recomendado)
```powershell
celery -A config worker -P solo -Q training -n worker-training@%COMPUTERNAME% -l INFO
```

### Opción 2: Pool Threads
```powershell
celery -A config worker --pool threads --concurrency 4 -Q training -n worker-training@%COMPUTERNAME% -l INFO
```

### Opción 3: Script PowerShell
```powershell
.\run_celery_worker.ps1
```

---

## 📊 Generar Datos de Prueba

### Con Script Automatizado (Sin API)
```powershell
python test_adaptive_ranking.py
```

### Con API (Requiere Servidor)
```powershell
# Terminal 1: Servidor
python manage.py runserver

# Terminal 2: Generar datos
python generate_test_data.py --queries 20 --feedback-ratio 0.8
```

---

## 🐛 Troubleshooting

### Error: Celery prefork en Windows
```powershell
# ❌ NO usar esto
celery -A config worker

# ✅ Usar esto
celery -A config worker -P solo -Q training -l INFO
```

### Error: Dataset vacío (NOOP_EMPTY_DATASET)
```powershell
# 1. Generar más feedback
python test_adaptive_ranking.py

# 2. Verificar pares
python manage.py shell -c "from ranking_adaptive.utils import build_pairwise_dataset; print(build_pairwise_dataset().n_pairs)"

# 3. Reducir ventana de días
python manage.py shell -c "from ranking_adaptive.tasks import train_signal_weights; print(train_signal_weights(days=7))"
```

### Error: ModuleNotFoundError
```powershell
# Instalar dependencias
pip install boto3 celery[redis]
```

---

## 📦 Migraciones

```powershell
# Crear migraciones
python manage.py makemigrations

# Aplicar migraciones
python manage.py migrate

# Ver migraciones pendientes
python manage.py showmigrations
```

---

## 🔐 Crear Usuario de Prueba

```powershell
python manage.py shell
```

```python
from django.contrib.auth import get_user_model
User = get_user_model()

user, created = User.objects.get_or_create(
    email="test@adaptive.local",
    defaults={
        "username": "test_adaptive",
        "is_active": True,
    }
)
if created:
    user.set_password("testpass123")
    user.save()
    print(f"✓ Usuario creado: {user.email}")
```

---

## 📈 Métricas Personalizadas

### Útil@Top10 (últimas 24h)
```powershell
python manage.py report_adaptive_metrics --hours 24
```

### Útil@Top10 (última semana)
```powershell
python manage.py report_adaptive_metrics --hours 168
```

### Contadores Rápidos
```powershell
python manage.py shell -c "from ranking_adaptive.models import RankingDecision; from apps.search.models import Feedback; print(f'Decisiones: {RankingDecision.objects.count()}, Feedbacks: {Feedback.objects.count()}')"
```

---

## 🎲 Probar A/B Testing

```powershell
python manage.py shell
```

```python
from apps.search.services.ask import ask
from django.contrib.auth import get_user_model

User = get_user_model()
user = User.objects.first()

# Generar varias consultas para ver distribución
for i in range(20):
    msg, hits = ask(user, f"Consulta de prueba {i}")
    print(f"Query {msg.id}: {hits[0].meta_json.get('experiment_bucket') if hits else 'N/A'}")
```

---

## 🔄 Rollback de Versión

```powershell
# 1. Listar versiones
python manage.py shell -c "from ranking_adaptive.models import RankingWeights; [print(w.version) for w in RankingWeights.objects.order_by('-created_at')]"

# 2. Activar versión anterior
python manage.py activate_ranking_weights w_PREV_VERSION
```

---

## 🧹 Limpiar Datos de Prueba

```powershell
python manage.py shell
```

```python
from apps.search.models import ChatSession, ChatMessage, SearchHit, Feedback
from apps.ranking_adaptive.models import RankingDecision, ExperimentAssignment

# ⚠️ CUIDADO: Esto borra TODOS los datos de prueba
user_email = "test@adaptive.local"

# Obtener usuario de prueba
from django.contrib.auth import get_user_model
User = get_user_model()
test_user = User.objects.filter(email=user_email).first()

if test_user:
    # Borrar sesiones del usuario de prueba
    ChatSession.objects.filter(user=test_user).delete()
    print("✓ Datos de prueba borrados")
else:
    print("✗ Usuario de prueba no encontrado")
```

---

## 📚 Documentación Completa

| Archivo | Descripción |
|---------|-------------|
| `ADAPTIVE_RANKING_VALIDATION.md` | Guía completa del flujo |
| `REPORTE_VALIDACION_FINAL.md` | Reporte de validación |
| `demo_celery_worker.md` | Guía de Celery en Windows |
| `COMANDOS_RAPIDOS.md` | Este archivo |

---

## 🎯 Flujo Típico de Desarrollo

```powershell
# 1. Verificar estado
python check_status.py

# 2. Generar datos de prueba
python test_adaptive_ranking.py

# 3. Verificar ETL
python manage.py shell -c "from ranking_adaptive.utils import build_pairwise_dataset; d=build_pairwise_dataset(); print(f'Pares: {d.n_pairs}')"

# 4. Entrenar (si hay pares > 0)
python manage.py shell -c "from ranking_adaptive.tasks import train_signal_weights; print(train_signal_weights())"

# 5. Activar versión (si entrenamiento exitoso)
python manage.py activate_ranking_weights w_YYYYMMDD_HHMMSS

# 6. Verificar métricas
python manage.py report_adaptive_metrics --hours 24

# 7. Verificar estado final
python check_status.py
```

---

## ⚡ One-Liners Útiles

```powershell
# Contar pares de entrenamiento
python manage.py shell -c "from ranking_adaptive.utils import build_pairwise_dataset; print(build_pairwise_dataset().n_pairs)"

# Ver versión activa
python manage.py shell -c "from ranking_adaptive.models import RankingWeights; w=RankingWeights.objects.filter(is_active=True).first(); print(w.version if w else 'None')"

# Contar feedback por tipo
python manage.py shell -c "from apps.search.models import Feedback; from django.db.models import Count; print(Feedback.objects.values('label').annotate(count=Count('id')))"

# Ver distribución de buckets
python manage.py shell -c "from apps.ranking_adaptive.models import ExperimentAssignment; from django.db.models import Count; print(ExperimentAssignment.objects.values('bucket').annotate(count=Count('id')))"
```

---

**Última actualización**: 2025-10-24  
**Versión**: 1.0
