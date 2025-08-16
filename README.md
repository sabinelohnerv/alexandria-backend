# Django + Postgres/Redis (Docker) + Whitelist + OTP por Email + JWT + Swagger

Proyecto base para estudio jurídico: **Django** local + **PostgreSQL** y **Redis** en **Docker**, gestión de **whitelist** (con rol `admin`/`user`), **registro con OTP por email (no TOTP)**, **login JWT** y **documentación Swagger/Redoc**.

## 🚀 Características
- **DBs en Docker**: `postgres:16-alpine`, `redis:7-alpine` (app Django corre local).
- **Whitelist**: CRUD admin + rol (`admin`/`user`), soft-delete, filtros/búsqueda/orden.
- **Registro en 2 pasos**: request OTP → confirm OTP (crea usuario con rol de whitelist).
- **Antiflood & Throttling**: cooldown en reenvío OTP + rate limit por IP/email.
- **Emails bonitos**: plantillas HTML + texto con branding (logo/color/CTA).
- **Auth JWT**: login, refresh, endpoint `/me`, `role` in-claim.
- **Swagger/Redoc**: esquema OpenAPI servido y exportable.

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
├─ config/                 # settings/urls/wsgi
├─ staff_whitelist/        # whitelist (modelo/servicio/serializers/views)
├─ accounts_signup/        # registro OTP (modelo/servicio/serializers/views)
├─ accounts_auth/          # login JWT (serializers/views)
├─ templates/
│  └─ emails/              # base_email.html, otp_email.html, otp_email.txt
├─ docker-compose.yml
├─ requirements.txt
├─ .env.example
├─ README.md
└─ .gitignore
```

## 🧪 Postman
Se incluye una colección de Postman para probar todos los endpoints (Whitelist, Registro, Auth).Importa el archivo **`postman_collection_whitelist_otp_jwt_v1.json`** en Postman (ajusta `base_url`, `admin_email`, etc.).

## 📨 Emails con plantillas
- HTML + texto (multipart) con `EmailMultiAlternatives`.
- Branding configurable por `.env` (`BRAND_*`, `FRONTEND_URL`).
- Vista de **preview** (opcional en DEBUG) para iterar diseño.

## ⛑️ Troubleshooting
- **`environ could not be resolved`** → activa el *venv* en VS Code y `pip install django-environ`.  Selecciona el intérprete: *Python: Select Interpreter* → `.venv`.
- **`connection refused` a Postgres/Redis** → `docker compose ps` y revisa `docker compose logs <servicio>`.
- **Puerto 5432 ocupado** → cambia mapeo `5433:5432` y ajusta `POSTGRES_PORT=5433`.
- **Email no llega** (en dev de consola solo imprime) → cambia a SMTP real o revisa logs.

## 📜 Licencia
MIT

---

> Última actualización: 2025-08-16
