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
from django.db import connection

from pulpcore import constants

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/1.11/howto/deployment/checklist/

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False

ALLOWED_HOSTS = ["*"]

MEDIA_ROOT = "/var/lib/pulp/"

ADMIN_SITE_URL = "admin/"

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/1.11/howto/static-files/

STATIC_URL = "/assets/"
STATIC_ROOT = os.path.join(MEDIA_ROOT, STATIC_URL.lstrip("/"))

DEFAULT_FILE_STORAGE = "pulpcore.app.models.storage.FileSystem"

FILE_UPLOAD_TEMP_DIR = os.path.join(MEDIA_ROOT, "tmp/")
WORKING_DIRECTORY = os.path.join(MEDIA_ROOT, "tmp/")
CHUNKED_UPLOAD_DIR = os.path.join(MEDIA_ROOT, "upload/")

# List of upload handler classes to be applied in order.
FILE_UPLOAD_HANDLERS = ("pulpcore.app.files.HashingFileUploadHandler",)

SECRET_KEY = True

# Application definition

INSTALLED_APPS = [
    # django stuff
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "import_export",
    # third-party
    "django_filters",
    "drf_spectacular",
    "guardian",
    "rest_framework",
    # pulp core app
    "pulpcore.app",
]

# Enumerate the installed Pulp plugins during the loading process for use in the status API
INSTALLED_PULP_PLUGINS = []

for entry_point in iter_entry_points("pulpcore.plugin"):
    plugin_app_config = entry_point.load()
    INSTALLED_PULP_PLUGINS.append(entry_point.module_name)
    INSTALLED_APPS.append(plugin_app_config)

# Optional apps that help with development, or augment Pulp in some non-critical way
OPTIONAL_APPS = [
    "crispy_forms",
    "django_extensions",
    "storages",
]

for app in OPTIONAL_APPS:
    # only import if app is installed
    with suppress(ImportError):
        import_module(app)
        INSTALLED_APPS.append(app)

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_currentuser.middleware.ThreadLocalUserMiddleware",
]

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "guardian.backends.ObjectPermissionBackend",
]

ROOT_URLCONF = "pulpcore.app.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [os.path.join(BASE_DIR, "templates")],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "pulpcore.app.wsgi.application"

REST_FRAMEWORK = {
    "URL_FIELD_NAME": "pulp_href",
    "DEFAULT_FILTER_BACKENDS": ("django_filters.rest_framework.DjangoFilterBackend",),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.LimitOffsetPagination",
    "PAGE_SIZE": 100,
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.BasicAuthentication",
    ),
    "UPLOADED_FILES_USE_URL": False,
    "DEFAULT_VERSIONING_CLASS": "rest_framework.versioning.URLPathVersioning",
    "DEFAULT_SCHEMA_CLASS": "pulpcore.openapi.PulpAutoSchema",
}

# Password validation
# https://docs.djangoproject.com/en/dev/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# Internationalization
# https://docs.djangoproject.com/en/1.11/topics/i18n/

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = "USE_I18N", True

USE_L10N = True

USE_TZ = True


# A set of default settings to use if the configuration file in
# /etc/pulp/ is missing or if it does not have values for every setting

# https://docs.djangoproject.com/en/1.11/ref/settings/#databases
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql_psycopg2",
        "NAME": "pulp",
        "USER": "pulp",
        "CONN_MAX_AGE": 0,
    },
}
# https://docs.djangoproject.com/en/1.11/ref/settings/#logging and
# https://docs.python.org/3/library/logging.config.html
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"simple": {"format": "pulp: %(name)s:%(levelname)s: %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "simple"}},
    "loggers": {
        "": {
            # The root logger
            "handlers": ["console"],
            "level": "INFO",
        },
    },
}

DRF_ACCESS_POLICY = {"reusable_conditions": "pulpcore.app.global_access_conditions"}

CONTENT_PATH_PREFIX = "/pulp/content/"
CONTENT_APP_TTL = 30

REMOTE_USER_ENVIRON_NAME = "REMOTE_USER"

ALLOWED_IMPORT_PATHS = []

ALLOWED_EXPORT_PATHS = []

PROFILE_STAGES_API = False

SPECTACULAR_SETTINGS = {
    "SERVE_URLCONF": ROOT_URLCONF,
    "DEFAULT_GENERATOR_CLASS": "pulpcore.openapi.PulpSchemaGenerator",
    "DEFAULT_SCHEMA_CLASS": "pulpcore.openapi.PulpAutoSchema",
    "COMPONENT_SPLIT_REQUEST": True,
    "COMPONENT_NO_READ_ONLY_REQUIRED": True,
    "TITLE": "Pulp 3 API",
    "DESCRIPTION": "Fetch, Upload, Organize, and Distribute Software Packages",
    "VERSION": "v3",
    "CONTACT": {
        "name": "Pulp Team",
        "email": "pulp-list@redhat.com",
        "url": "https://pulpproject.org",
    },
    "LICENSE": {
        "name": "GPLv2+",
        "url": "https://raw.githubusercontent.com/pulp/pulpcore/master/LICENSE",
    },
}


# What kinds of checksums is this pulp-instance _allowed to use_ ?
# NOTE : "sha256"" IS REQUIRED - Pulp will fail to start if it is not found in this set
# NOTE: specifying checksums that are not listed under ALL_KNOWN_CONTENT_CHECKSUMS will fail
#       at startup
ALLOWED_CONTENT_CHECKSUMS = ["md5", "sha1", "sha224", "sha256", "sha384", "sha512"]

# HERE STARTS DYNACONF EXTENSION LOAD (Keep at the very bottom of settings.py)
# Read more at https://dynaconf.readthedocs.io/en/latest/guides/django.html
import dynaconf  # noqa

settings = dynaconf.DjangoDynaconf(
    __name__,
    GLOBAL_ENV_FOR_DYNACONF="PULP",
    ENV_SWITCHER_FOR_DYNACONF="PULP_ENV",
    PRELOAD_FOR_DYNACONF=[
        "{}.app.settings".format(plugin_name) for plugin_name in INSTALLED_PULP_PLUGINS
    ],
    ENVVAR_FOR_DYNACONF="PULP_SETTINGS",
)
# HERE ENDS DYNACONF EXTENSION LOAD (No more code below this line)

try:
    CONTENT_ORIGIN
except NameError:
    raise ImproperlyConfigured(
        _(
            "CONTENT_ORIGIN is a required setting but it was not configured. This may be caused "
            "by invalid read permissions of the settings file. Note that CONTENT_ORIGIN is set by "
            "the installer automatically."
        )
    )

# Check legality of ALLOWED_CONTENT_CHECKSUMS post-dynaconf-load, in case it has been overridden
# in a site-specific location (eg, in /etc/pulp/settings.py)
if "sha256" not in ALLOWED_CONTENT_CHECKSUMS:
    raise ImproperlyConfigured(
        _(
            "ALLOWED_CONTENT_CHECKSUMS MUST contain 'sha256' - Pulp's content-storage-addressing "
            "relies on sha256 to identify entities."
        )
    )

unknown_algs = set(ALLOWED_CONTENT_CHECKSUMS).difference(constants.ALL_KNOWN_CONTENT_CHECKSUMS)
if unknown_algs:
    raise ImproperlyConfigured(
        _(
            "ALLOWED_CONTENT_CHECKSUMS may only contain algorithms known to pulp - see "
            "constants.ALL_KNOWN_CONTENT_CHECKSUMS for the allowed list. Unknown algorithms "
            "provided: {}".format(unknown_algs)
        )
    )
try:
    for checksum in ALLOWED_CONTENT_CHECKSUMS:
        # can't import Artifact here so use a direct db connection
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT count(pulp_id) FROM core_artifact WHERE {checksum} IS NULL")
            row = cursor.fetchone()
            if row[0] > 0:
                raise ImproperlyConfigured(
                    _(
                        "ALLOWED_CONTENT_CHECKSUMS cannot contain checksum '{}' since checksums "
                        "can only be removed and not added to ALLOWED_CONTENT_CHECKSUMS in "
                        "existing deployments."
                    ).format(checksum)
                )
except ImproperlyConfigured as e:
    raise e
except Exception:
    # our check could fail if the table hasn't been created yet or we can't get a db connection
    pass
finally:
    connection.close()
