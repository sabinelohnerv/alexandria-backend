# Setup - Dashboard de Ranking Adaptativo

Guía rápida de instalación y configuración.

## Instalación

La app ya está integrada en el proyecto. Solo necesitas:

### 1. Verificar Configuración

Asegúrate de que la app está en `config/settings.py`:

```python
INSTALLED_APPS = [
    # ...
    "apps.ranking_adaptive",
    "apps.ranking_dashboard",
]
```

### 2. Aplicar Migraciones

```bash
python manage.py migrate
```

### 3. Crear Usuario Staff

Si no tienes un usuario staff, créalo:

```bash
python manage.py createsuperuser
```

O convierte un usuario existente en staff:

```bash
python manage.py shell
```

```python
from django.contrib.auth import get_user_model
User = get_user_model()
user = User.objects.get(email='tu_email@example.com')
user.is_staff = True
user.save()
```

### 4. Iniciar Servidor

```bash
python manage.py runserver
```

### 5. Acceder al Dashboard

Navega a: `http://localhost:8000/ranking/`

## Primer Uso

### Opción A: Entrenar Primera Versión

1. Ve a `/ranking/train/`
2. Usa parámetros por defecto
3. Click "Iniciar Entrenamiento"
4. Espera a que complete
5. Ve a `/ranking/versions/`
6. Evalúa y activa la nueva versión

### Opción B: Ciclo Completo

1. Ve a `/ranking/cycle/`
2. Marca "Activar automáticamente"
3. Click "Ejecutar Ciclo Completo"
4. Revisa el output

## Requisitos Previos

Para que el entrenamiento funcione, necesitas:

1. **Datos de feedback**: Usuarios deben haber dado feedback (útil/no útil)
2. **Decisiones de ranking**: El sistema debe haber registrado decisiones
3. **Ventana temporal**: Al menos algunos días de datos

### Verificar Datos

```bash
python manage.py shell
```

```python
from apps.search.models import Feedback
from apps.ranking_adaptive.models import RankingDecision

# Verificar feedback
print(f"Feedbacks: {Feedback.objects.filter(hit__isnull=False).count()}")

# Verificar decisiones
print(f"Decisiones: {RankingDecision.objects.count()}")
```

Si no hay datos suficientes, el entrenamiento mostrará: "No hay datos suficientes para entrenar"

## Configuración Avanzada

### Cambiar Color Primary

En `.env`:

```
BRAND_PRIMARY_COLOR=#023f66
```

### Ajustar Parámetros por Defecto

Edita los valores por defecto en los templates:
- `train.html`: Parámetros de entrenamiento
- `cycle.html`: Parámetros del ciclo
- `export.html`: Ventana de exportación

### Personalizar Navegación

Edita `templates/ranking_dashboard/base.html` para agregar/quitar enlaces.

## Troubleshooting

### No puedo acceder (403 Forbidden)

Tu usuario no tiene permisos de staff. Ejecuta:

```bash
python manage.py shell
```

```python
from django.contrib.auth import get_user_model
User = get_user_model()
user = User.objects.get(email='TU_EMAIL')
user.is_staff = True
user.save()
```

### "No hay datos suficientes para entrenar"

Necesitas acumular más feedback de usuarios. Opciones:

1. Espera a que usuarios reales usen el sistema
2. Genera datos de prueba (solo desarrollo)
3. Reduce la ventana temporal (ej: 7 días en vez de 30)

### Error al ejecutar comandos

Verifica que los comandos funcionan desde CLI:

```bash
python manage.py list_ranking_versions
python manage.py train_ranking_weights --days 30
```

Si fallan desde CLI, el problema está en los comandos, no en el dashboard.

## Integración con CI/CD

### Ejemplo: GitHub Actions

```yaml
name: Deploy Dashboard

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Run migrations
        run: python manage.py migrate
      - name: Collect static
        run: python manage.py collectstatic --noinput
```

## Seguridad

### Producción

En producción, asegúrate de:

1. **HTTPS**: Usa SSL/TLS
2. **CSRF**: Habilitado por defecto en Django
3. **Session Security**: Configura `SESSION_COOKIE_SECURE = True`
4. **Staff Only**: Los decoradores ya validan `is_staff`

### Auditoría

Todas las acciones quedan registradas en:
- Logs de Django
- Mensajes del sistema
- Timestamps en modelos (`created_at`)

## Monitoreo

### Métricas Clave

Monitorea:
- Número de versiones creadas por semana
- Tiempo de entrenamiento
- Métricas de evaluación (útil@top10)
- Frecuencia de rollbacks

### Logs

Los comandos generan output detallado que se muestra en el dashboard.
Para logs persistentes, configura logging en `settings.py`.

## Próximos Pasos

1. Acumula datos de feedback
2. Entrena primera versión
3. Evalúa métricas
4. Activa si es satisfactoria
5. Monitorea rendimiento
6. Re-entrena semanalmente

---

**¿Necesitas ayuda?** Consulta el README.md para documentación completa.
