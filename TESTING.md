# Documentación de Testing - Alexandria Backend

## 📋 Resumen

Esta suite de pruebas cubre los módulos principales del backend de Alexandria, proporcionando una cobertura de aproximadamente **16%** del código base con **149 tests** automatizados.

## 🎯 Módulos Cubiertos

La suite de tests cubre los siguientes módulos principales:

### 1. **staff_whitelist** - Gestión de Lista Blanca
- ✅ Modelo `StaffWhitelist`
- ✅ Servicio `StaffWhitelistService`
- ✅ API endpoints (CRUD completo)
- ✅ Soft delete y reactivación
- ✅ Filtros y búsqueda

**Tests incluidos:** 25 tests
- Creación y validación de entradas
- Normalización de emails
- Validación de roles (admin/user)
- Operaciones de desactivación/reactivación
- Endpoints de API con autenticación
- Verificación pública de whitelist

### 2. **accounts_signup** - Registro de Usuarios
- ✅ Modelo `PendingRegistration`
- ✅ Flujo completo de OTP
- ✅ Servicios de registro
- ✅ API endpoints

**Tests incluidos:** 28 tests
- Solicitud de OTP
- Confirmación de OTP
- Reenvío de OTP con cooldown
- Validación de whitelist
- Expiración de códigos
- Máximo de intentos
- Estado de registro
- Normalización de emails

### 3. **accounts_auth** - Autenticación JWT
- ✅ Login con JWT
- ✅ Refresh de tokens
- ✅ Endpoint `/me`
- ✅ Logout con blacklist
- ✅ Claims personalizados

**Tests incluidos:** 21 tests
- Login exitoso y fallido
- Validación de credenciales
- Refresh de tokens
- Información del usuario autenticado
- Logout y blacklist de tokens
- Claims personalizados (role, email, name)
- Case-insensitive email

### 4. **accounts_password** - Recuperación de Contraseña
- ✅ Modelo `PasswordResetTicket`
- ✅ Flujo completo de reset
- ✅ Servicios de recuperación
- ✅ API endpoints

**Tests incluidos:** 22 tests
- Solicitud de reset
- Reenvío de OTP
- Confirmación y cambio de contraseña
- Validación de códigos
- Expiración y cooldown
- Máximo de intentos
- Seguridad (no revela existencia de usuarios)

### 5. **documents** - Gestión de Documentos
- ✅ Modelo `Document`
- ✅ Modelo `Chunk`
- ✅ Relaciones y cascadas
- ✅ Querysets y filtros

**Tests incluidos:** 18 tests
- Creación de documentos
- Metadatos y estados
- Chunks y ordenamiento
- Relaciones documento-chunk
- Cascade delete
- Filtros por fuente, estado, año

### 6. **search** - Búsqueda y Chat
- ✅ Modelo `ChatSession`
- ✅ Modelo `ChatMessage`
- ✅ Modelo `SearchHit`
- ✅ Modelo `Feedback`
- ✅ API endpoints principales

**Tests incluidos:** 35 tests
- Sesiones de chat (CRUD)
- Soft delete y restauración
- Mensajes y ordenamiento
- Hits de búsqueda con scores
- Feedback (útil/no útil)
- Aislamiento de usuarios
- Autenticación requerida

## 🚀 Configuración del Entorno de Testing

### Requisitos Previos

1. **Python 3.10+**
2. **Docker** (para PostgreSQL y Redis)
3. **Entorno virtual activado**

### Instalación de Dependencias

```bash
# Activar entorno virtual
.venv\Scripts\Activate.ps1  # Windows PowerShell
# source .venv/bin/activate  # Linux/Mac

# Instalar dependencias de testing
pip install pytest pytest-django pytest-cov factory-boy faker

# Instalar dependencias del proyecto
pip install -r requirements.txt
```

### Configuración de Base de Datos

```bash
# Levantar servicios de Docker
docker compose up -d postgres redis

# Verificar que estén corriendo
docker compose ps
```

## 📝 Archivos de Configuración

### pytest.ini
```ini
[pytest]
DJANGO_SETTINGS_MODULE = config.settings
python_files = tests.py test_*.py *_tests.py
python_classes = Test*
python_functions = test_*
addopts = 
    --verbose
    --strict-markers
    --tb=short
    --cov=apps
    --cov-report=html
    --cov-report=term-missing
    --cov-config=.coveragerc
    --reuse-db
    --nomigrations
markers =
    unit: Unit tests
    integration: Integration tests
    slow: Slow running tests
testpaths = tests
```

### .coveragerc
```ini
[run]
source = apps
omit = 
    */migrations/*
    */tests.py
    */test_*.py
    */__pycache__/*
    */admin.py
    */apps.py

[report]
exclude_lines =
    pragma: no cover
    def __repr__
    def __str__
    raise AssertionError
    raise NotImplementedError
```

## 🧪 Ejecutar Tests

### Todos los Tests
```bash
python -m pytest tests/ -v
```

### Tests con Cobertura
```bash
python -m pytest tests/ --cov=apps --cov-report=html --cov-report=term-missing
```

### Tests por Módulo
```bash
# Staff Whitelist
python -m pytest tests/test_staff_whitelist.py -v

# Accounts Signup
python -m pytest tests/test_accounts_signup.py -v

# Accounts Auth
python -m pytest tests/test_accounts_auth.py -v

# Accounts Password
python -m pytest tests/test_accounts_password.py -v

# Documents
python -m pytest tests/test_documents.py -v

# Search
python -m pytest tests/test_search.py -v
```

### Tests Específicos
```bash
# Por clase
python -m pytest tests/test_staff_whitelist.py::TestStaffWhitelistModel -v

# Por test individual
python -m pytest tests/test_accounts_auth.py::TestJWTLoginAPI::test_login_success -v

# Por palabra clave
python -m pytest tests/ -k "login" -v
```

### Tests sin Cobertura (más rápido)
```bash
python -m pytest tests/ -v --no-cov
```

## 📊 Reporte de Cobertura

Después de ejecutar los tests con cobertura, se genera un reporte HTML en `htmlcov/index.html`:

```bash
# Abrir reporte en navegador (Windows)
start htmlcov/index.html

# Linux/Mac
open htmlcov/index.html
```

### Cobertura Actual por Módulo

| Módulo | Cobertura | Tests |
|--------|-----------|-------|
| **staff_whitelist** | ~20% | 25 |
| **accounts_signup** | ~22% | 28 |
| **accounts_auth** | Variable | 21 |
| **accounts_password** | ~26% | 22 |
| **documents** | ~100% (modelos) | 18 |
| **search** | ~89% (modelos) | 35 |
| **TOTAL** | **~16%** | **149** |

## 🏗️ Estructura de Tests

```
tests/
├── __init__.py
├── test_staff_whitelist.py      # 25 tests
├── test_accounts_signup.py      # 28 tests
├── test_accounts_auth.py        # 21 tests
├── test_accounts_password.py    # 22 tests
├── test_documents.py            # 18 tests
└── test_search.py               # 35 tests

conftest.py                       # Fixtures globales
pytest.ini                        # Configuración de pytest
.coveragerc                       # Configuración de cobertura
```

## 🔧 Fixtures Disponibles

### Fixtures de Usuario
```python
@pytest.fixture
def user_factory(db):
    """Factory para crear usuarios de prueba"""
    
@pytest.fixture
def admin_user(user_factory):
    """Usuario administrador"""
    
@pytest.fixture
def regular_user(user_factory):
    """Usuario regular"""
```

### Fixtures de Cliente API
```python
@pytest.fixture
def api_client():
    """Cliente API de DRF"""
    
@pytest.fixture
def authenticated_client(api_client, regular_user):
    """Cliente autenticado con usuario regular"""
    
@pytest.fixture
def admin_client(api_client, admin_user):
    """Cliente autenticado con usuario administrador"""
```

### Fixtures de Whitelist
```python
@pytest.fixture
def whitelist_factory(db, admin_user):
    """Factory para crear entradas de whitelist"""
```

### Fixtures de Documentos y Search
```python
@pytest.fixture
def document_factory(db):
    """Factory para crear documentos"""
    
@pytest.fixture
def chunk_factory(db):
    """Factory para crear chunks"""
    
@pytest.fixture
def session_factory(db):
    """Factory para crear sesiones de chat"""
```

## 📖 Ejemplos de Uso

### Ejemplo 1: Test de Modelo
```python
@pytest.mark.django_db
def test_create_whitelist_entry(admin_user):
    """Prueba creación de entrada en whitelist"""
    entry = StaffWhitelist.objects.create(
        email="test@example.com",
        first_name="Test",
        last_name="User",
        role=StaffWhitelist.Role.USER,
        created_by=admin_user
    )
    assert entry.email == "test@example.com"
    assert entry.is_active is True
```

### Ejemplo 2: Test de API
```python
@pytest.mark.django_db
def test_login_success(api_client, regular_user):
    """Prueba login exitoso"""
    data = {
        "email": "user@example.com",
        "password": "testpass123"
    }
    response = api_client.post("/api/auth/login/", data)
    assert response.status_code == status.HTTP_200_OK
    assert "access" in response.data
    assert "refresh" in response.data
```

### Ejemplo 3: Test de Servicio
```python
@pytest.mark.django_db
def test_request_otp_success(whitelist_factory):
    """Prueba solicitud exitosa de OTP"""
    whitelist_factory(email="test@example.com")
    request_registration_otp(
        email="test@example.com",
        password="testpass123"
    )
    
    pending = PendingRegistration.objects.get(email="test@example.com")
    assert len(pending.otp_code) == 6
    assert len(mail.outbox) == 1
```

## 🎯 Mejores Prácticas

### 1. Nomenclatura de Tests
- Usar nombres descriptivos: `test_<acción>_<resultado>`
- Ejemplo: `test_login_with_invalid_credentials_fails`

### 2. Organización
- Agrupar tests relacionados en clases
- Usar `@pytest.mark.django_db` para tests que usan la BD
- Usar fixtures para setup común

### 3. Assertions
- Usar assertions específicos
- Verificar tanto el caso exitoso como los errores
- Probar edge cases

### 4. Aislamiento
- Cada test debe ser independiente
- No depender del orden de ejecución
- Limpiar datos después de cada test (pytest lo hace automáticamente)

## 🐛 Troubleshooting

### Error: "No module named 'celery'"
```bash
pip install celery redis django-redis
```

### Error: "No module named 'environ'"
```bash
pip install django-environ
```

### Error: "No module named 'psycopg'"
```bash
pip install psycopg psycopg-binary psycopg2-binary
```

### Error: "Connection refused" a PostgreSQL/Redis
```bash
# Verificar que Docker esté corriendo
docker compose ps

# Levantar servicios
docker compose up -d postgres redis
```

### Tests muy lentos
```bash
# Usar --reuse-db para reutilizar la BD entre ejecuciones
python -m pytest tests/ --reuse-db

# Usar --nomigrations para no ejecutar migraciones
python -m pytest tests/ --nomigrations

# Ejecutar en paralelo (requiere pytest-xdist)
pip install pytest-xdist
python -m pytest tests/ -n auto
```

## 📈 Próximos Pasos

### Áreas para Expandir Cobertura

1. **Views y Serializers** (actualmente 0%)
   - Agregar tests de validación de serializers
   - Probar todos los endpoints de API
   - Validar respuestas y códigos de estado

2. **Servicios Complejos** (20-30%)
   - Servicios de ranking y búsqueda
   - Procesamiento de documentos
   - Generación de embeddings

3. **Tasks de Celery** (0%)
   - Tasks de procesamiento de documentos
   - Tasks de ranking adaptativo
   - Tasks de embeddings

4. **Throttling y Permisos** (0%)
   - Validar rate limiting
   - Probar permisos personalizados
   - Verificar throttling por IP/email

5. **Integration Tests**
   - Flujos completos end-to-end
   - Integración con servicios externos (MinIO, OpenAI)
   - Tests de performance

### Recomendaciones

- **Objetivo de Cobertura:** Alcanzar 80% en módulos críticos
- **CI/CD:** Integrar tests en pipeline de CI/CD
- **Tests de Regresión:** Agregar tests para bugs encontrados
- **Documentación:** Mantener documentación actualizada

## 📚 Recursos Adicionales

- [Pytest Documentation](https://docs.pytest.org/)
- [pytest-django Documentation](https://pytest-django.readthedocs.io/)
- [Django Testing Documentation](https://docs.djangoproject.com/en/stable/topics/testing/)
- [DRF Testing Documentation](https://www.django-rest-framework.org/api-guide/testing/)

## 📝 Notas Finales

Esta suite de tests proporciona una base sólida para el testing del backend de Alexandria. Los tests cubren los flujos principales de autenticación, gestión de usuarios, documentos y búsqueda. 

**Cobertura Actual:** ~16% (149 tests)
**Objetivo Recomendado:** 80% en módulos críticos

Para contribuir con más tests, seguir la estructura y convenciones establecidas en los archivos existentes.

---

**Última actualización:** Octubre 2025
**Versión:** 1.0.0
