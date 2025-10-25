# Quick Start - Dashboard de Ranking Adaptativo

Guía de inicio rápido en 5 minutos.

## 1. Crear Usuario Staff (1 min)

```bash
python manage.py createsuperuser
```

Ingresa:
- Email
- Password
- Confirma password

El superusuario automáticamente tiene `is_staff=True`.

## 2. Iniciar Servidor (30 seg)

```bash
python manage.py runserver
```

## 3. Acceder al Dashboard (30 seg)

Abre tu navegador en:

```
http://localhost:8000/ranking/
```

Login con las credenciales del paso 1.

## 4. Primera Ejecución (3 min)

### Opción A: Ciclo Completo (Recomendado)

1. Click en **"Ciclo Completo"**
2. Deja los valores por defecto
3. NO marques "Activar automáticamente" (primera vez)
4. Click **"Ejecutar Ciclo Completo"**
5. Espera 1-2 minutos
6. Revisa el output

### Opción B: Paso a Paso

1. Click en **"Entrenar Nueva Versión"**
2. Deja los valores por defecto:
   - Ventana: 30 días
   - Learning rate: 0.005
   - Pasos: 800
   - L2: 0.2
3. Click **"Iniciar Entrenamiento"**
4. Espera 30-60 segundos
5. Ve a **"Gestionar Versiones"**
6. Click **"Evaluar"** en la nueva versión
7. Revisa métricas
8. Si es satisfactoria, click **"Activar"**

## 5. Verificar (30 seg)

Ve al Dashboard principal:
- Deberías ver la versión activa
- Total de versiones: 1 o más
- Estado: Operativo

## Comandos Rápidos (Alternativa CLI)

Si prefieres CLI:

```bash
# Entrenar
python manage.py train_ranking_weights --days 30

# Listar
python manage.py list_ranking_versions

# Evaluar (reemplaza VERSION con el nombre real)
python manage.py evaluate_ranking_model --version VERSION --compare

# Activar
python manage.py activate_ranking_weights VERSION
```

## Ciclo Completo CLI

```bash
python manage.py run_training_cycle --days 30
```

## Troubleshooting Rápido

### "No hay datos suficientes para entrenar"

**Causa**: No hay feedback de usuarios aún.

**Solución temporal**: Reduce la ventana temporal:
```bash
python manage.py train_ranking_weights --days 7
```

O espera a acumular más datos de usuarios reales.

### Error 403 al acceder

**Causa**: Usuario no es staff.

**Solución**:
```bash
python manage.py shell
```

```python
from django.contrib.auth import get_user_model
User = get_user_model()
user = User.objects.get(email='TU_EMAIL')
user.is_staff = True
user.save()
exit()
```

### No aparece nada en el dashboard

**Causa**: No hay versiones entrenadas.

**Solución**: Entrena la primera versión (ver paso 4).

## Próximo Paso

Una vez que tengas la primera versión:

1. **Monitorea**: Ve a Dashboard y revisa métricas
2. **Re-entrena**: Semanalmente o cuando tengas más datos
3. **Compara**: Usa la opción "comparar" al evaluar
4. **Rollback**: Si algo falla, usa "Rollback a Anterior"

## Navegación Rápida

- **Dashboard**: `/ranking/`
- **Entrenar**: `/ranking/train/`
- **Versiones**: `/ranking/versions/`
- **Ciclo Completo**: `/ranking/cycle/`
- **Exportar**: `/ranking/export/`

## Atajos de Teclado

En el dashboard:
- Navegación superior para cambiar de página
- Botones con confirmación para acciones críticas
- Formularios con valores por defecto sensatos

## Tips

1. **Primera vez**: No uses auto-activación, revisa métricas primero
2. **Producción**: Usa ciclo completo con auto-activación solo si confías en los datos
3. **Desarrollo**: Experimenta con diferentes parámetros
4. **Rollback**: Siempre disponible si algo sale mal

## Recursos

- **Documentación completa**: `README.md`
- **Setup detallado**: `SETUP.md`
- **Resumen del sistema**: `/RANKING_SYSTEM_SUMMARY.md` (raíz del proyecto)

---

**Tiempo total**: ~5 minutos
**Dificultad**: Fácil
**Requisitos**: Python, Django, navegador web
