# Manejo de Errores en AskView

## Resumen

Se ha implementado un sistema robusto de manejo de errores en `AskView` para capturar y manejar apropiadamente todos los tipos de errores que pueden ocurrir durante la generación de respuestas.

## Tipos de Errores Manejados

### 1. Errores de Validación de Consulta (400 Bad Request)

**Código de error:** `not_legal`, `too_vague`, `too_short`, `empty_query`

**Causa:** La consulta no pasa los guards de validación (no es jurídica, es muy vaga, muy corta o vacía).

**Respuesta:**
```json
{
  "detail": "Este asistente responde exclusivamente consultas jurídicas. Por favor, formula tu pregunta con enfoque legal.",
  "code": "not_legal"
}
```

**Status HTTP:** `400 BAD REQUEST`

---

### 2. Errores de Base de Datos (503 Service Unavailable)

**Código de error:** `database_error`

**Causa:** 
- Problemas de conexión con la base de datos
- Errores de transacción
- Base de datos no disponible
- Errores de integridad de datos

**Respuesta al recuperar sesión:**
```json
{
  "detail": "Error de base de datos. Por favor, intenta nuevamente.",
  "code": "database_error"
}
```

**Respuesta durante generación:**
```json
{
  "detail": "Error de base de datos al procesar tu consulta. Por favor, intenta nuevamente.",
  "code": "database_error"
}
```

**Status HTTP:** `503 SERVICE UNAVAILABLE`

**Logging:** Se registra el error completo con stack trace en los logs del servidor.

---

### 3. Errores de Conexión (503 Service Unavailable)

**Código de error:** `connection_error`

**Causa:**
- Error de conexión con servicios externos (LLM, embeddings, reranker)
- Problemas de red
- Servicios externos no disponibles

**Respuesta:**
```json
{
  "detail": "Error de conexión con los servicios externos. Por favor, intenta nuevamente.",
  "code": "connection_error"
}
```

**Status HTTP:** `503 SERVICE UNAVAILABLE`

**Logging:** Se registra el error completo con stack trace en los logs del servidor.

---

### 4. Errores de Timeout (504 Gateway Timeout)

**Código de error:** `timeout_error`

**Causa:**
- La consulta tardó demasiado tiempo en procesarse
- Servicios externos no responden a tiempo
- Consulta muy compleja

**Respuesta:**
```json
{
  "detail": "La solicitud tardó demasiado tiempo. Por favor, intenta con una consulta más específica.",
  "code": "timeout_error"
}
```

**Status HTTP:** `504 GATEWAY TIMEOUT`

**Logging:** Se registra el error completo con stack trace en los logs del servidor.

---

### 5. Errores Inesperados (500 Internal Server Error)

**Código de error:** `internal_error`

**Causa:**
- Cualquier error no anticipado
- Errores de programación
- Excepciones no manejadas específicamente

**Respuesta:**
```json
{
  "detail": "Ocurrió un error inesperado al procesar tu consulta. Por favor, intenta nuevamente.",
  "code": "internal_error"
}
```

**Status HTTP:** `500 INTERNAL SERVER ERROR`

**Logging:** Se registra el error completo con stack trace en los logs del servidor.

---

### 6. Otros Errores HTTP

#### Session Not Found (404)
```json
{
  "detail": "Session not found"
}
```
**Status:** `404 NOT FOUND`

#### Forbidden (403)
```json
{
  "detail": "Forbidden"
}
```
**Status:** `403 FORBIDDEN`

#### Session Deleted (410)
```json
{
  "detail": "Session was deleted"
}
```
**Status:** `410 GONE`

---

## Flujo de Manejo de Errores

```
1. Validación de datos (serializer)
   ↓
2. Guards de consulta jurídica
   ↓ [QueryGuardException] → 400 Bad Request
   ↓
3. Validación de sesión (si existe)
   ↓ [DoesNotExist] → 404 Not Found
   ↓ [DatabaseError] → 503 Service Unavailable
   ↓ [Permisos] → 403 Forbidden
   ↓ [Deleted] → 410 Gone
   ↓
4. Generación de respuesta (ask_service)
   ↓ [DatabaseError] → 503 Service Unavailable
   ↓ [ConnectionError] → 503 Service Unavailable
   ↓ [TimeoutError] → 504 Gateway Timeout
   ↓ [Exception] → 500 Internal Server Error
   ↓
5. Respuesta exitosa → 200 OK
```

---

## Logging

Todos los errores se registran usando el logger de Python con nivel `ERROR` e incluyen:

- Mensaje descriptivo del error
- Stack trace completo (`exc_info=True`)
- Contexto del error (fase en la que ocurrió)

**Ejemplo de log:**
```python
logger.error(f"Database error during ask_service: {e}", exc_info=True)
```

Los logs se pueden consultar en:
- Consola de desarrollo
- Archivos de log configurados en Django settings
- Sistemas de monitoreo (Sentry, CloudWatch, etc.)

---

## Mejores Prácticas Implementadas

### 1. Mensajes Amigables al Usuario
- Mensajes en español, claros y accionables
- No exponen detalles técnicos internos
- Sugieren acciones al usuario ("intenta nuevamente", "consulta más específica")

### 2. Códigos de Error Estructurados
- Cada tipo de error tiene un código único
- Permite al frontend manejar errores específicamente
- Facilita debugging y monitoreo

### 3. Status HTTP Apropiados
- `400`: Error del cliente (validación)
- `403`: Sin permisos
- `404`: Recurso no encontrado
- `410`: Recurso eliminado
- `500`: Error del servidor
- `503`: Servicio no disponible
- `504`: Timeout

### 4. Logging Completo
- Todos los errores se registran
- Stack traces completos para debugging
- Contexto adicional en mensajes de log

### 5. Separación de Errores
- Errores de validación vs errores de sistema
- Errores recuperables vs no recuperables
- Errores de cliente vs errores de servidor

---

## Ejemplo de Uso en Frontend

```javascript
try {
  const response = await fetch('/api/ask/', {
    method: 'POST',
    body: JSON.stringify({ query: userQuery }),
    headers: { 'Content-Type': 'application/json' }
  });
  
  if (!response.ok) {
    const error = await response.json();
    
    switch (error.code) {
      case 'not_legal':
      case 'too_vague':
        // Mostrar mensaje de validación
        showValidationError(error.detail);
        break;
        
      case 'database_error':
      case 'connection_error':
        // Mostrar mensaje de error temporal, sugerir reintentar
        showTemporaryError(error.detail);
        break;
        
      case 'timeout_error':
        // Sugerir simplificar la consulta
        showTimeoutError(error.detail);
        break;
        
      case 'internal_error':
        // Mostrar error genérico, contactar soporte
        showInternalError(error.detail);
        break;
        
      default:
        showGenericError(error.detail);
    }
    return;
  }
  
  const data = await response.json();
  displayAnswer(data);
  
} catch (error) {
  // Error de red del cliente
  showNetworkError('No se pudo conectar con el servidor');
}
```

---

## Testing

Para probar el manejo de errores:

### 1. Simular Error de Base de Datos
```python
# En tests
from unittest.mock import patch
from django.db import OperationalError

@patch('apps.search.views.ChatSession.objects.get')
def test_database_error(mock_get):
    mock_get.side_effect = OperationalError("Connection lost")
    response = client.post('/api/ask/', data={'query': 'test legal query'})
    assert response.status_code == 503
    assert response.json()['code'] == 'database_error'
```

### 2. Simular Error de Conexión
```python
@patch('apps.search.services.ask.ask_service')
def test_connection_error(mock_ask):
    mock_ask.side_effect = ConnectionError("Service unavailable")
    response = client.post('/api/ask/', data={'query': 'test legal query'})
    assert response.status_code == 503
    assert response.json()['code'] == 'connection_error'
```

### 3. Simular Timeout
```python
@patch('apps.search.services.ask.ask_service')
def test_timeout_error(mock_ask):
    mock_ask.side_effect = TimeoutError("Request timeout")
    response = client.post('/api/ask/', data={'query': 'test legal query'})
    assert response.status_code == 504
    assert response.json()['code'] == 'timeout_error'
```

---

## Monitoreo

### Métricas Recomendadas

1. **Tasa de errores por tipo**
   - Porcentaje de requests con cada código de error
   - Tendencias temporales

2. **Latencia de errores**
   - Tiempo hasta que ocurre el error
   - Identificar cuellos de botella

3. **Errores por usuario**
   - Usuarios afectados por errores
   - Patrones de uso problemáticos

4. **Recuperación de errores**
   - Tasa de retry exitoso
   - Tiempo de recuperación del servicio

### Alertas Recomendadas

- **Alta tasa de errores 500**: > 5% de requests
- **Alta tasa de errores 503**: > 10% de requests
- **Alta tasa de timeouts**: > 2% de requests
- **Spike de errores**: Aumento súbito > 50%

---

## Mejoras Futuras

1. **Retry automático**: Para errores transitorios (503)
2. **Circuit breaker**: Para servicios externos
3. **Rate limiting por error**: Prevenir abuse después de errores
4. **Mensajes personalizados**: Según contexto del usuario
5. **Telemetría detallada**: Traces distribuidos
6. **Fallback responses**: Respuestas parciales en caso de error
