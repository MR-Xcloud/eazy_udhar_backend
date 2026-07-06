"""
Django settings for easyudhar project.
All secrets and environment-specific values live in .env — see .env.example.
"""

from datetime import timedelta
import json
from pathlib import Path

from easyudhar.env import env, env_bool, env_int, env_list, load_env_file

BASE_DIR = Path(__file__).resolve().parent.parent
load_env_file(BASE_DIR)

# ── Core ─────────────────────────────────────────────────────────────────────
SECRET_KEY = env('DJANGO_SECRET_KEY')
if not SECRET_KEY:
    raise ValueError('DJANGO_SECRET_KEY is required. Copy .env.example to .env and set it.')

DEBUG = env_bool('DJANGO_DEBUG', 'false')

ALLOWED_HOSTS = env_list('ALLOWED_HOSTS') or ['localhost', '127.0.0.1']
if DEBUG and '*' not in ALLOWED_HOSTS:
    ALLOWED_HOSTS = list(dict.fromkeys([*ALLOWED_HOSTS, 'localhost', '127.0.0.1']))

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'corsheaders',
    'rest_framework',
    'rest_framework_simplejwt',
    'customerapp',
    'sellerapp',
    'adminapp',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'easyudhar.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'easyudhar.wsgi.application'

# ── Database ─────────────────────────────────────────────────────────────────
_db_engine = env('DB_ENGINE', 'sqlite').lower()
if _db_engine == 'mysql':
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.mysql',
            'NAME': env('DB_NAME', 'eazyudhar'),
            'USER': env('DB_USER', 'eazyudhar'),
            'PASSWORD': env('DB_PASSWORD'),
            'HOST': env('DB_HOST', '127.0.0.1'),
            'PORT': env('DB_PORT', '3306'),
            'CONN_MAX_AGE': env_int('DB_CONN_MAX_AGE', '60'),
            'OPTIONS': {
                'charset': 'utf8mb4',
                'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
            },
        },
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / env('SQLITE_PATH', 'db.sqlite3'),
            'OPTIONS': {'timeout': 30},
        },
    }

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = env('TIME_ZONE', 'Asia/Kolkata')
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / env('STATIC_ROOT', 'staticfiles')
MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / env('MEDIA_ROOT', 'media')

AUTH_USER_MODEL = 'customerapp.Customer'
AUTHENTICATION_BACKENDS = [
    'adminapp.authentication.AdminBackend',
    'sellerapp.authentication.SellerBackend',
    'django.contrib.auth.backends.ModelBackend',
]

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=env_int('JWT_ACCESS_TOKEN_MINUTES', '60')),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=env_int('JWT_REFRESH_TOKEN_DAYS', '30')),
    'ROTATE_REFRESH_TOKENS': True,
}

# ── Firebase (FCM) ───────────────────────────────────────────────────────────
FIREBASE_PROJECT_ID = env('FIREBASE_PROJECT_ID')
FIREBASE_CREDENTIALS_PATH = env('FIREBASE_CREDENTIALS_PATH')
FIREBASE_USE_ADC = env('FIREBASE_USE_ADC')

_default_firebase_creds = BASE_DIR / 'firebase' / 'service-account.json'
if not FIREBASE_CREDENTIALS_PATH and _default_firebase_creds.exists():
    FIREBASE_CREDENTIALS_PATH = str(_default_firebase_creds)
if not FIREBASE_CREDENTIALS_PATH:
    for _candidate in sorted((BASE_DIR / 'firebase').glob('*firebase-adminsdk*.json')):
        FIREBASE_CREDENTIALS_PATH = str(_candidate)
        break
if not FIREBASE_PROJECT_ID:
    _google_services = BASE_DIR / 'firebase' / 'google-services.json'
    if _google_services.exists():
        try:
            with open(_google_services, encoding='utf-8') as _f:
                FIREBASE_PROJECT_ID = json.load(_f).get('project_id', '').strip()
        except (OSError, json.JSONDecodeError):
            pass
if not FIREBASE_PROJECT_ID and FIREBASE_CREDENTIALS_PATH:
    try:
        with open(FIREBASE_CREDENTIALS_PATH, encoding='utf-8') as _f:
            FIREBASE_PROJECT_ID = json.load(_f).get('project_id', '').strip()
    except (OSError, json.JSONDecodeError):
        pass

# ── Nimbus SMS ─────────────────────────────────────────────────────────────────
NIMBUS_SMS_ENABLED = env_bool('NIMBUS_SMS_ENABLED', 'true')
NIMBUS_USER_ID = env('NIMBUS_USER_ID')
NIMBUS_PASSWORD = env('NIMBUS_PASSWORD')
NIMBUS_AUTH_KEY = env('NIMBUS_AUTH_KEY')
NIMBUS_DLT_ENTITY_ID = env('NIMBUS_DLT_ENTITY_ID')
NIMBUS_SENDER_ID = env('NIMBUS_SENDER_ID')
NIMBUS_API_URL = env('NIMBUS_API_URL', 'http://nimbusit.net/api/pushsms')
NIMBUS_CREDIT_TEMPLATE_ID = env('NIMBUS_CREDIT_TEMPLATE_ID')
NIMBUS_PAYMENT_TEMPLATE_ID = env('NIMBUS_PAYMENT_TEMPLATE_ID')
NIMBUS_OTP_TEMPLATE_ID = env('NIMBUS_OTP_TEMPLATE_ID')
NIMBUS_OTP_SMS_TEXT = env('NIMBUS_OTP_SMS_TEXT')
NIMBUS_CREDIT_SMS_TEXT = env('NIMBUS_CREDIT_SMS_TEXT')
NIMBUS_PAYMENT_SMS_TEXT = env('NIMBUS_PAYMENT_SMS_TEXT')
NIMBUS_REMINDER_TEMPLATE_ID = env('NIMBUS_REMINDER_TEMPLATE_ID')
NIMBUS_REMINDER_SMS_TEXT = env('NIMBUS_REMINDER_SMS_TEXT')
NIMBUS_SUMMARY_TEMPLATE_ID = env('NIMBUS_SUMMARY_TEMPLATE_ID')
PUBLIC_STATEMENT_BASE_URL = env('PUBLIC_STATEMENT_BASE_URL').rstrip('/')
PUBLIC_STATEMENT_SMS_HOST = env('PUBLIC_STATEMENT_SMS_HOST')
NIMBUS_SMS_PLATFORM_NAME = env('NIMBUS_SMS_PLATFORM_NAME', 'EAZYUDHAR')
NIMBUS_SMS_VAR_MAX_LENGTH = env_int('NIMBUS_SMS_VAR_MAX_LENGTH', '30')
NIMBUS_SMS_LINK_VAR_MAX_LENGTH = env_int('NIMBUS_SMS_LINK_VAR_MAX_LENGTH', '0')
NIMBUS_MOBILE_PREFIX = env('NIMBUS_MOBILE_PREFIX')
NIMBUS_SMS_CATEGORY = env('NIMBUS_SMS_CATEGORY')
NIMBUS_SMS_SUB_CATEGORY = env('NIMBUS_SMS_SUB_CATEGORY')
NIMBUS_SMS_EXTRA_PARAMS = env('NIMBUS_SMS_EXTRA_PARAMS')
NIMBUS_REQUEST_TIMEOUT = env_int('NIMBUS_REQUEST_TIMEOUT', '30')
NIMBUS_WAIT_DELIVERY_REPORT = env_bool('NIMBUS_WAIT_DELIVERY_REPORT', 'false')

# ── Chat / bill image uploads ─────────────────────────────────────────────────
IMAGE_UPLOAD_MAX_DIMENSION = env_int('IMAGE_UPLOAD_MAX_DIMENSION', '1024')
IMAGE_UPLOAD_JPEG_QUALITY = env_int('IMAGE_UPLOAD_JPEG_QUALITY', '75')
IMAGE_UPLOAD_MIN_JPEG_QUALITY = env_int('IMAGE_UPLOAD_MIN_JPEG_QUALITY', '35')
IMAGE_UPLOAD_MIN_DIMENSION = env_int('IMAGE_UPLOAD_MIN_DIMENSION', '480')
IMAGE_UPLOAD_MAX_BYTES = env_int('IMAGE_UPLOAD_MAX_BYTES', str(64 * 1024))

# ── CORS / CSRF ───────────────────────────────────────────────────────────────
_cors = env_list('CORS_ALLOWED_ORIGINS')
if DEBUG:
    _cors.extend(
        [
            'http://localhost:8080',
            'http://127.0.0.1:8080',
            'http://localhost:5173',
            'http://127.0.0.1:5173',
            'http://localhost:8022',
            'http://127.0.0.1:8022',
        ]
    )
CORS_ALLOWED_ORIGINS = list(dict.fromkeys(_cors))
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
]

_csrf = env_list('CSRF_TRUSTED_ORIGINS')
if DEBUG:
    _csrf.extend(['http://localhost:8000', 'http://127.0.0.1:8000'])
CSRF_TRUSTED_ORIGINS = list(dict.fromkeys(_csrf))

if env_bool('BEHIND_HTTPS_PROXY'):
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_SECURE = True

# ── Email (Postmark OTP) ───────────────────────────────────────────────────────
POSTMARK_SERVER_TOKEN = env('POSTMARK_SERVER_TOKEN')
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = env('EMAIL_HOST', 'smtp.postmarkapp.com')
EMAIL_PORT = env_int('EMAIL_PORT', '587')
EMAIL_HOST_USER = env('EMAIL_HOST_USER') or POSTMARK_SERVER_TOKEN
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD') or POSTMARK_SERVER_TOKEN
EMAIL_USE_TLS = env_bool('EMAIL_USE_TLS', 'true')
EMAIL_USE_SSL = env_bool('EMAIL_USE_SSL', 'false')
EMAIL_TIMEOUT = env_int('EMAIL_TIMEOUT', '30')
DEFAULT_FROM_EMAIL = env('OTP_FROM_EMAIL')
OTP_EMAIL_SUBJECT = env('OTP_EMAIL_SUBJECT', 'Your EAZYUDHAR login code')
OTP_EXPIRY_MINUTES = env_int('OTP_EXPIRY_MINUTES', '5')
OTP_RESEND_COOLDOWN_SECONDS = env_int('OTP_RESEND_COOLDOWN_SECONDS', '60')
OTP_EMAIL_LOGO_URL = env('OTP_EMAIL_LOGO_URL')

# ── WhatsApp (optional) ────────────────────────────────────────────────────────
WHATSAPP_API_ENABLED = env_bool('WHATSAPP_API_ENABLED', 'false')
WHATSAPP_ACCESS_TOKEN = env('WHATSAPP_ACCESS_TOKEN')
WHATSAPP_PHONE_NUMBER_ID = env('WHATSAPP_PHONE_NUMBER_ID')
WHATSAPP_API_VERSION = env('WHATSAPP_API_VERSION', 'v21.0')

# ── Razorpay ───────────────────────────────────────────────────────────────────
RAZORPAY_MODE = env('RAZORPAY_MODE', 'test').lower()
RAZORPAY_TEST_KEY_ID = env('RAZORPAY_TEST_KEY_ID')
RAZORPAY_TEST_KEY_SECRET = env('RAZORPAY_TEST_SECRET') or env('RAZORPAY_TEST_KEY_SECRET')
RAZORPAY_TEST_WEBHOOK_SECRET = env('RAZORPAY_TEST_WEBHOOK_SECRET')
RAZORPAY_LIVE_KEY_ID = env('RAZORPAY_LIVE_KEY_ID')
RAZORPAY_LIVE_KEY_SECRET = env('RAZORPAY_LIVE_KEY_SECRET')
RAZORPAY_LIVE_WEBHOOK_SECRET = env('RAZORPAY_LIVE_WEBHOOK_SECRET')
RAZORPAY_ROUTE_ENABLED = env_bool('RAZORPAY_ROUTE_ENABLED', 'false')

# ── SQLite WAL (local dev only) ────────────────────────────────────────────────
if _db_engine != 'mysql':

    def _configure_sqlite_connection(sender, connection, **kwargs):
        if connection.vendor == 'sqlite':
            with connection.cursor() as cursor:
                cursor.execute('PRAGMA journal_mode=WAL;')
                cursor.execute('PRAGMA busy_timeout=30000;')

    from django.db.backends.signals import connection_created

    connection_created.connect(_configure_sqlite_connection)
