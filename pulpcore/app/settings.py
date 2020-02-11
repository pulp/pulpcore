"""
Django settings for the Pulp Platform application

Never import this module directly, instead `from django.conf import settings`, see
https://docs.djangoproject.com/en/1.11/topics/settings/#using-settings-in-python-code

For the full list of settings and their values, see
https://docs.djangoproject.com/en/1.11/ref/settings/
"""

import os
from contextlib import suppress
from gettext import gettext as _
from importlib import import_module
from pkg_resources import iter_entry_points

from django.core.exceptions import ImproperlyConfigured


# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/1.11/howto/deployment/checklist/

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False

ALLOWED_HOSTS = ['*']

MEDIA_ROOT = '/var/lib/pulp/'
STATIC_ROOT = os.path.join(MEDIA_ROOT, 'assets/')

DEFAULT_FILE_STORAGE = 'pulpcore.app.models.storage.FileSystem'

FILE_UPLOAD_TEMP_DIR = os.path.join(MEDIA_ROOT, 'tmp/')
WORKING_DIRECTORY = os.path.join(MEDIA_ROOT, 'tmp/')

# List of upload handler classes to be applied in order.
FILE_UPLOAD_HANDLERS = ('pulpcore.app.files.HashingFileUploadHandler',)

SECRET_KEY = True

# Application definition

INSTALLED_APPS = [
    # django stuff
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # third-party
    'django_filters',
    'drf_yasg',
    'rest_framework',
    # pulp core app
    'pulpcore.app',
]

# Enumerate the installed Pulp plugins during the loading process for use in the status API
INSTALLED_PULP_PLUGINS = []

for entry_point in iter_entry_points('pulpcore.plugin'):
    plugin_app_config = entry_point.load()
    INSTALLED_PULP_PLUGINS.append(entry_point.module_name)
    INSTALLED_APPS.append(plugin_app_config)

# Optional apps that help with development, or augment Pulp in some non-critical way
OPTIONAL_APPS = [
    'crispy_forms',
    'django_extensions',
    'storages',
]

for app in OPTIONAL_APPS:
    # only import if app is installed
    with suppress(ImportError):
        import_module(app)
        INSTALLED_APPS.append(app)

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
]

ROOT_URLCONF = 'pulpcore.app.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'pulpcore.app.wsgi.application'

REST_FRAMEWORK = {
    'URL_FIELD_NAME': 'pulp_href',
    'DEFAULT_FILTER_BACKENDS': ('django_filters.rest_framework.DjangoFilterBackend',),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.LimitOffsetPagination',
    'PAGE_SIZE': 100,
    'DEFAULT_PERMISSION_CLASSES': ('rest_framework.permissions.IsAuthenticated',),
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.BasicAuthentication',
    ),
    'UPLOADED_FILES_USE_URL': False,
    'DEFAULT_VERSIONING_CLASS': 'rest_framework.versioning.URLPathVersioning',
}

# Password validation
# https://docs.djangoproject.com/en/dev/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/1.11/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = 'USE_I18N', True

USE_L10N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/1.11/howto/static-files/

STATIC_URL = '/static/'

# A set of default settings to use if the configuration file in
# /etc/pulp/ is missing or if it does not have values for every setting

# https://docs.djangoproject.com/en/1.11/ref/settings/#databases
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql_psycopg2',
        'NAME': 'pulp',
        'USER': 'pulp',
        'CONN_MAX_AGE': 0,
    },
}
# https://docs.djangoproject.com/en/1.11/ref/settings/#logging and
# https://docs.python.org/3/library/logging.config.html
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'simple': {'format': 'pulp: %(name)s:%(levelname)s: %(message)s'},
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'simple'
        }
    },
    'loggers': {
        '': {
            # The root logger
            'handlers': ['console'],
            'level': 'INFO'
        },
    }
}

CONTENT_PATH_PREFIX = '/pulp/content/'
CONTENT_APP_TTL = 30

REMOTE_USER_ENVIRON_NAME = "REMOTE_USER"

ALLOWED_IMPORT_PATHS = []

PROFILE_STAGES_API = False

SWAGGER_SETTINGS = {
    'DEFAULT_GENERATOR_CLASS': 'pulpcore.app.openapigenerator.PulpOpenAPISchemaGenerator',
    'DEFAULT_AUTO_SCHEMA_CLASS': 'pulpcore.app.openapigenerator.PulpAutoSchema',
    'DEFAULT_INFO': 'pulpcore.app.urls.api_info',
}

# have the docs url show field descriptions with html
REDOC_SETTINGS = {
    'SPEC_URL': '/pulp/api/v3/docs/?format=openapi&include_html=1',
}

# HERE STARTS DYNACONF EXTENSION LOAD (Keep at the very bottom of settings.py)
# Read more at https://dynaconf.readthedocs.io/en/latest/guides/django.html
import dynaconf  # noqa
settings = dynaconf.DjangoDynaconf(
    __name__,
    GLOBAL_ENV_FOR_DYNACONF='PULP',
    ENV_SWITCHER_FOR_DYNACONF='PULP_ENV',
    PRELOAD_FOR_DYNACONF=[
        '{}.app.settings'.format(plugin_name)
        for plugin_name in INSTALLED_PULP_PLUGINS
    ],
    ENVVAR_FOR_DYNACONF='PULP_SETTINGS',
)
# HERE ENDS DYNACONF EXTENSION LOAD (No more code below this line)


try:
    CONTENT_ORIGIN
except NameError:
    raise ImproperlyConfigured(_('You must specify the CONTENT_ORIGIN setting.'))
