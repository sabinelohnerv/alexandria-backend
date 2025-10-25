# Dashboard de Ranking Adaptativo

Interfaz web minimalista para gestionar el sistema de ranking adaptativo.

## Características

- **Validación de usuario staff**: Solo usuarios con `is_staff=True` pueden acceder
- **Gestión de versiones**: Listar, evaluar, activar y hacer rollback de versiones
- **Entrenamiento**: Ejecutar entrenamiento con parámetros configurables
- **Ciclo completo**: Pipeline automatizado de entrenamiento, evaluación y activación
- **Exportación**: Exportar datos de entrenamiento para análisis offline
- **UI moderna**: Interfaz limpia con Tailwind CSS

## Acceso

**URL**: `http://localhost:8000/ranking/`

**Requisitos**:
- Usuario autenticado
- Usuario con permisos de staff (`is_staff=True`)

## Páginas Disponibles

### 1. Dashboard Principal (`/ranking/`)
- Vista general del sistema
- Versión activa actual
- Total de versiones
- Acciones rápidas
- Tabla de versiones recientes

### 2. Entrenar Nueva Versión (`/ranking/train/`)
- Configurar parámetros de entrenamiento:
  - Ventana de datos (días)
  - Learning rate
  - Pasos de optimización
  - Regularización L2
- Ejecuta comando `train_ranking_weights`

### 3. Gestión de Versiones (`/ranking/versions/`)
- Lista completa de versiones
- Estado (activa/inactiva)
- Acciones por versión:
  - Evaluar
  - Activar
- Botón de rollback rápido

### 4. Evaluación (`/ranking/versions/<version>/evaluate/`)
- Métricas de rendimiento
- Comparación con versión anterior
- Análisis de pesos
- Opción de activar desde evaluación

### 5. Ciclo Completo (`/ranking/cycle/`)
- Pipeline automatizado completo
- Opción de auto-activación
- Muestra output completo del proceso

### 6. Exportar Datos (`/ranking/export/`)
- Exporta datos a JSON
- Configurable por ventana temporal
- Archivo: `training_export.json`

## Seguridad

### Validación de Acceso

Todas las vistas están protegidas con:

```python
@login_required
@user_passes_test(is_staff)
```

Si un usuario no autenticado intenta acceder, será redirigido al login.
Si un usuario autenticado pero no staff intenta acceder, recibirá un error 403.

### Confirmaciones

Las acciones críticas requieren confirmación:
- Activar versión
- Rollback a versión anterior
- Ejecutar ciclo completo

## Integración

### Settings

La app está registrada en `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    # ...
    "apps.ranking_adaptive",
    "apps.ranking_dashboard",
]
```

### URLs

Montada en `/ranking/`:

```python
urlpatterns = [
    # ...
    path("ranking/", include("apps.ranking_dashboard.urls")),
]
```

## Uso Típico

### Flujo Manual

1. Acceder a `/ranking/`
2. Click en "Entrenar Nueva Versión"
3. Configurar parámetros y entrenar
4. Ir a "Gestionar Versiones"
5. Click en "Evaluar" para la nueva versión
6. Revisar métricas
7. Click en "Activar" si es satisfactoria

### Flujo Automatizado

1. Acceder a `/ranking/`
2. Click en "Ciclo Completo"
3. Configurar días de datos
4. Marcar "Activar automáticamente" (opcional)
5. Ejecutar ciclo
6. Revisar output completo

### Rollback Rápido

1. Ir a "Gestionar Versiones"
2. Click en "Rollback a Anterior"
3. Confirmar acción

## Comandos Ejecutados

El dashboard ejecuta estos comandos de Django:

- `train_ranking_weights`: Entrenar nueva versión
- `list_ranking_versions`: Listar versiones
- `evaluate_ranking_model`: Evaluar versión
- `activate_ranking_weights`: Activar versión
- `activate_prev_weights`: Rollback
- `run_training_cycle`: Ciclo completo
- `export_training_data`: Exportar datos

## Diseño

### Colores

- **Primary**: `#023f66` (definido en `BRAND_PRIMARY_COLOR`)
- **Success**: Verde
- **Warning**: Amarillo
- **Error**: Rojo

### Framework CSS

- **Tailwind CSS**: Cargado desde CDN
- **Responsive**: Diseño adaptable a móviles

### Componentes

- Navegación superior con enlaces principales
- Sistema de mensajes (success, error, warning)
- Tablas responsivas
- Formularios con validación
- Botones con estados hover

## Estructura de Archivos

```
apps/ranking_dashboard/
├── __init__.py
├── apps.py
├── views.py              # Lógica de vistas
├── urls.py               # Rutas
├── templates/
│   └── ranking_dashboard/
│       ├── base.html     # Template base
│       ├── home.html     # Dashboard principal
│       ├── train.html    # Formulario de entrenamiento
│       ├── versions.html # Lista de versiones
│       ├── evaluate.html # Evaluación de versión
│       ├── cycle.html    # Formulario de ciclo completo
│       ├── cycle_result.html # Resultado del ciclo
│       └── export.html   # Formulario de exportación
└── README.md
```

## Mensajes del Sistema

El dashboard usa el sistema de mensajes de Django:

- **Success**: Operaciones completadas exitosamente
- **Warning**: Advertencias (ej: sin datos suficientes)
- **Error**: Errores durante ejecución

Los mensajes se muestran en la parte superior de cada página.

## Personalización

### Cambiar Color Primary

Editar en `.env`:

```
BRAND_PRIMARY_COLOR=#023f66
```

O directamente en `base.html`:

```javascript
tailwind.config = {
    theme: {
        extend: {
            colors: {
                primary: '#023f66',
            }
        }
    }
}
```

### Agregar Nueva Vista

1. Crear función en `views.py`
2. Agregar decoradores de seguridad
3. Crear template en `templates/ranking_dashboard/`
4. Agregar ruta en `urls.py`
5. Agregar enlace en navegación (`base.html`)

## Troubleshooting

### Error 403: Forbidden

**Causa**: Usuario no tiene permisos de staff.

**Solución**: Otorgar permisos de staff al usuario:

```python
python manage.py shell
>>> from django.contrib.auth import get_user_model
>>> User = get_user_model()
>>> user = User.objects.get(email='usuario@example.com')
>>> user.is_staff = True
>>> user.save()
```

### Error: Template not found

**Causa**: Templates no están en la ubicación correcta.

**Solución**: Verificar que los templates están en:
`apps/ranking_dashboard/templates/ranking_dashboard/`

### Comandos no se ejecutan

**Causa**: Error en los comandos de management.

**Solución**: Verificar logs y ejecutar comandos manualmente:

```bash
python manage.py train_ranking_weights --days 30
```

## Desarrollo

### Agregar Nueva Métrica

1. Modificar `evaluate_ranking_model` command
2. Actualizar vista `evaluate_version` en `views.py`
3. Actualizar template `evaluate.html`

### Agregar Nuevo Parámetro de Entrenamiento

1. Agregar campo en `train.html`
2. Capturar en vista `train_weights` en `views.py`
3. Pasar a `call_command('train_ranking_weights', ...)`

## Notas

- El dashboard NO modifica directamente la base de datos
- Todas las operaciones se ejecutan a través de comandos de Django
- Los comandos tienen su propia lógica de validación y seguridad
- El dashboard es solo una interfaz conveniente sobre los comandos CLI

---

**Versión**: 1.0.0
**Última actualización**: 2025-10-25
