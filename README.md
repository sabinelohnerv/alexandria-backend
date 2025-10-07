# ALEXANDRIA (ASISTENTE DE INVESTIGACIÓN JURÍDICA) - BACKEND

Proyecto base para estudio jurídico: **Django** local + **PostgreSQL** y **Redis** en **Docker**, gestión de **whitelist** (con rol `admin`/`user`), **registro con OTP por email**, **login JWT**, **recuperación de contraseña con OTP por email**, **ask**, **sessions**.

## 🚀 Características
- **DBs en Docker**: `postgres:16-alpine`, `redis:7-alpine` (app Django corre local).
- **Whitelist**: CRUD admin + rol (`admin`/`user`), soft-delete, filtros/búsqueda/orden.
- **Registro en 2 pasos**: request OTP → confirm OTP (crea usuario con rol de whitelist).
- **Antiflood & Throttling**: cooldown en reenvío OTP + rate limit por IP/email.
- **Emails bonitos**: plantillas HTML + texto con branding (logo/color/CTA).
- **Auth JWT**: login, refresh, endpoint `/me`, `role` in-claim.

## 📦 Requisitos
- Python **3.10+**
- Docker / Docker Compose
- PostgreSQL y Redis **no** locales (los levanta Docker)
- (Opcional) Make / GNU tools

## 🧩 Instalación rápida
```bash
# 1) Clonar y entrar
git clone <https://github.com/sabinelohnerv/alexandria-backend.git>.git
cd <https://github.com/sabinelohnerv/alexandria-backend.git>

# 2) Crear venv e instalar
python -m venv .venv
# PowerShell:
. .venv/Scripts/Activate.ps1
# macOS/Linux:
# source .venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt  

# 3) Levantar Postgres + Redis
docker compose up -d

# 4) Configurar variables
cp .env.example .env  # edita según tu entorno

# 5) Migraciones + admin
python manage.py migrate
python manage.py createsuperuser

# 6) Correr servidor
python manage.py runserver
```

Accede a:
- App: http://127.0.0.1:8000/
- Admin: http://127.0.0.1:8000/admin/

## 🔧 Variables de entorno (`.env` ejemplo)
```env
# Django
DEBUG=True
SECRET_KEY=dev-secret-change-me
ALLOWED_HOSTS=127.0.0.1,localhost
TIME_ZONE=America/La_Paz

# Postgres (Docker)
POSTGRES_DB=appdb
POSTGRES_USER=appuser
POSTGRES_PASSWORD=app_password
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432      # usa 5433 si cambiaste el mapeo del puerto

# Redis (Docker)
REDIS_URL=redis://127.0.0.1:6379/1

# Email
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
DEFAULT_FROM_EMAIL=no-reply@sanjines.com
# Si usas SMTP real:
# EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
# EMAIL_HOST=smtp.tu_proveedor.com
# EMAIL_PORT=587
# EMAIL_HOST_USER=tu_usuario
# EMAIL_HOST_PASSWORD=tu_password
# EMAIL_USE_TLS=True

# Branding (emails)
BRAND_NAME=Sanjinés & Asociados
BRAND_PRIMARY_COLOR=#1E88E5
BRAND_LOGO_URL=
FRONTEND_URL=http://localhost:3000
```

## 🗂️ Estructura sugerida
```
.
├─ config/                    # settings/urls/wsgi/asgi
├─ common/
│  └─ services/
│     └─ minio_storage.py     # presign_get_url (MinIO/S3)
├─ documents/                 # Document, Chunk, etc.
├─ search/                    # ChatSession, ChatMessage, SearchHit, Feedback
├─ staff_whitelist/           # whitelist (roles y acceso)
├─ accounts_signup/           # registro OTP
├─ accounts_auth/             # login JWT
├─ accounts_password/         # reset por OTP
├─ templates/emails/          # base_email.html + plantillas
├─ docker-compose.yml
├─ requirements.txt
├─ .env.example
└─ README.md
```
---
## 🔎 API de Búsqueda & Chats (Alexandria)

Todas las rutas requieren **JWT** en `Authorization: Bearer <token>`. La paginación estándar de DRF aplica donde se indique (`?page=1`).

### 1) Sesiones de chat
```
GET    /api/sessions/                     # lista mis sesiones (con soft-deleted opcional)
POST   /api/sessions/                     # crea sesión (title opcional)
GET    /api/sessions/{id}/                # detalle
PATCH  /api/sessions/{id}/                # renombrar (title)
DELETE /api/sessions/{id}/                # soft delete
POST   /api/sessions/{id}/restore/        # restaurar soft delete
```

**Query params útiles**
- `include_deleted=1` (incluir soft-deleted)
- `all=1` (solo staff/superuser para ver de todos)

**Ejemplo**
```bash
curl -H "Authorization: Bearer $JWT" http://localhost:8000/api/sessions/
```

---

### 2) Mensajes de una sesión
```
GET /api/sessions/{session_id}/messages/
```
Devuelve cada mensaje anotado con feedback agregado:
- `useful_count`, `not_useful_count`
- `my_feedback_label` ∈ { "useful", "not_useful", null }

**Ejemplo**
```bash
curl -H "Authorization: Bearer $JWT" \
  http://localhost:8000/api/sessions/123/messages/
```

**Respuesta (parcial)**
```json
{
  "id": 981,
  "role": "assistant",
  "text": "Respuesta...",
  "useful_count": 3,
  "not_useful_count": 1,
  "my_feedback_label": "useful"
}
```

---

### 3) Preguntar (ASK)
```
POST /api/ask/
```
**Body**
```json
{ "query": "¿Doctrina sobre cosa juzgada constitucional?", "session_id": 123 }
```
Si no envías `session_id`, se crea una nueva sesión y se responde ahí.

**Respuesta (parcial)**
```json
{
  "message": { "id": 981, "role":"assistant", "text":"..." },
  "hits": [ { "id":101, "rank":1, "document_id":55, "chunk_id":4421 } ]
}
```

---

### 4) Feedback por **mensaje**
```
POST   /api/feedback/                     # crear/actualizar voto (idempotente)
DELETE /api/feedback?message_id={id}      # quitar voto (unvote)
```
**Body (POST)**
```json
{ "message": 981, "label": "useful", "comment": "" }
```
`label` ∈ { `useful`, `not_useful` }.

---

### 5) Hits de un mensaje (con metadatos legibles)
```
GET /api/sessions/{session_id}/messages/{message_id}/hits/
```
**Query params**
- `include_snippet=1` → añade `snippet` (extracto del chunk)
- `limit=N` (si no usas paginación DRF)

**Respuesta (parcial)**
```json
{
  "id": 101,
  "rank": 1,
  "score_vector": 0.82,
  "score_lexical": 7.2,
  "score_rerank": 0.91,
  "document": {
    "id": 55, "title": "SCP 0123/2023", "authority": "TCP",
    "doc_type": "sentencia", "number": "0123/2023",
    "year": "2023", "published_date": "2023-09-18", "state": "vigente"
  },
  "chunk": { "id": 4421, "ordinal": 12, "section": "Fundamentos jurídicos", "token_count": 182 },
  "snippet": "Considerando III: La jurisprudencia..."
}
```

---

### 6) Archivo del documento asociado a un hit (MinIO / presigned URL)
```
GET /api/sessions/{session_id}/messages/{message_id}/hits/{hit_id}/file/
```
**Respuesta:** `302 Found` con cabecera **`Location`** apuntando al presigned URL (válido por pocos minutos).  
Úsalo directo en `<iframe src=".../file/">` o `window.open()`; MinIO sirve `Range` para visor PDF.

**Ejemplo**
```bash
curl -i -H "Authorization: Bearer $JWT" \
  http://localhost:8000/api/sessions/123/messages/981/hits/7/file/
# HTTP/1.1 302 Found
# Location: https://minio.local/alexandria/...X-Amz-Signature=...
```

---

## 🧪 Postman
Se incluye colecciones de Postman para probar todos los endpoints (Whitelist, Registro, Auth).Importa en Postman (ajusta `base_url`, `admin_email`, etc.) y prueba.

## 📨 Emails con plantillas
- HTML + texto (multipart) con `EmailMultiAlternatives`.

## ⛑️ Troubleshooting
- **`environ could not be resolved`** → activa el *venv* en VS Code y `pip install django-environ`.  Selecciona el intérprete: *Python: Select Interpreter* → `.venv`.
- **`connection refused` a Postgres/Redis** → `docker compose ps` y revisa `docker compose logs <servicio>`.
- **Puerto 5432 ocupado** → cambia mapeo `5433:5432` y ajusta `POSTGRES_PORT=5433`.
- **Email no llega** (en dev de consola solo imprime) → cambia a SMTP real o revisa logs.
- **302 MinIO pero no abre** → revisa que el navegador permita popups y que el presigned URL no haya expirado (expira en `MINIO_PRESIGN_EXPIRES`).

---

## 📜 Licencia
MIT License

---

> Última actualización: 2025-10-07
