"""
Django settings for mundo_kids project.
"""

from pathlib import Path
import os
import environ
import pymysql
pymysql.install_as_MySQLdb()

# Inicialização do environ
env = environ.Env()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Carregar .env se existir
if os.path.exists(os.path.join(BASE_DIR, '.env')):
    environ.Env.read_env(os.path.join(BASE_DIR, '.env'))

# Quick-start development settings - unsuitable for production
SECRET_KEY = env('SECRET_KEY', default='django-insecure-hm_2#$g22uyn(+mjyh5wv%byen-zx5yaw_z&g%)#_d88=j@!gu')

DEBUG = env('DEBUG', default=False)

ALLOWED_HOSTS = [
    'app.mundokidscz.com.br',  # domínio de produção
    '.vercel.app',
    'localhost',
    '127.0.0.1',
    '192.168.2.10',
    '192.168.2.8',
    '192.168.2.9',
    '192.168.2.6',
    '3b5d0bbeeeeb.ngrok-free.app',
    '192.168.3.9',
    '192.168.18.28'
]

# Em HTTPS o Django exige a origem na lista para aceitar formulários (login,
# salvar orçamento, pedido do catálogo...); sem isso dá "Proibido (403) CSRF"
CSRF_TRUSTED_ORIGINS = [
    'https://app.mundokidscz.com.br',
    'https://*.vercel.app',
]

# Atrás de proxy (Vercel/nginx) a conexão chega ao Django como http; o proxy
# informa o https original neste cabeçalho
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Application definition
INSTALLED_APPS = [
    'whitenoise.runserver_nostatic',  
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    "accounts",
    "orcamentos",
    'relatorios',
    'dbbackup',
    'whatsapp',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    # Comprime as páginas (o Django 5 já inclui a proteção contra BREACH)
    'django.middleware.gzip.GZipMiddleware',
    # Tira a indentação do HTML antes de comprimir (ver mundo_kids/middleware.py)
    'mundo_kids.middleware.CompactarHTMLMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'mundo_kids.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'accounts.context_processors.empresa_theme',
                'orcamentos.context_processors.pedidos_catalogo',
            ],
        },
    },
]

WSGI_APPLICATION = 'mundo_kids.wsgi.application'

# Database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Se tiver variáveis de MySQL no .env, use-as
if env('DB_ENGINE', default='') == 'django.db.backends.mysql':
    DATABASES = {
        'default': {
            'ENGINE': env('DB_ENGINE'),
            'NAME': env('DB_NAME'),
            'USER': env('DB_USER'),
            'PASSWORD': env('DB_PASSWORD'),
            'HOST': env('DB_HOST'),
            'PORT': env('DB_PORT', default='3306'),
        },
        'sqlite_backup': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Internationalization
LANGUAGE_CODE = 'pt-br'
TIME_ZONE = 'America/Sao_Paulo'  # Corrigido
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = '/static/'
#STATIC_DIR = os.path.join(BASE_DIR, 'static')
#STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

# Endereço público usado nos links do catálogo online enviados aos clientes.
# Como o banco é o mesmo, o link gerado em qualquer lugar (até no PC) funciona
# no domínio de produção. Pode ser trocado pela variável CATALOGO_URL_BASE no .env.
CATALOGO_URL_BASE = env('CATALOGO_URL_BASE', default='https://app.mundokidscz.com.br')

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
USE_L10N = True
USE_THOUSAND_SEPARATOR = True

# Configuração do modelo de usuário personalizado
AUTH_USER_MODEL = 'accounts.Usuario'
LOGIN_REDIRECT_URL = '/orcamentos/'  
LOGIN_URL = '/accounts/login/'       
LOGOUT_REDIRECT_URL = '/accounts/login/'  

# Application definition
DBBACKUP_STORAGE = 'django.core.files.storage.FileSystemStorage'
DBBACKUP_STORAGE_OPTIONS = {'location': os.path.join(BASE_DIR, 'backups')}

# Forçar a extensão .sql no nome do arquivo
DBBACKUP_FILENAME_TEMPLATE = 'backup-{datetime}.sql'
DBBACKUP_DATE_FORMAT = '%Y-%m-%d-%H%M%S'

DBBACKUP_CONNECTION = {
    'default': {
        'DUMP_SUFFIX': '.sql',
    }
}

# configurações da api do whatsapp
WHATSAPP_TOKEN = env('WHATSAPP_TOKEN', default=None)
WHATSAPP_PHONE_ID = env('WHATSAPP_PHONE_ID', default=None)
WHATSAPP_VERIFY_TOKEN = env('WHATSAPP_VERIFY_TOKEN', default='meu_token_verificacao')