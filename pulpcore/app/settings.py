"""
Django settings for the Pulp Platform application

Never import this module directly, instead `from django.conf import settings`, see
https://docs.djangoproject.com/en/3.2/topics/settings/#using-settings-in-python-code

For the full list of settings and their values, see
https://docs.djangoproject.com/en/3.2/ref/settings/
"""

import sys

from contextlib import suppress
from importlib import import_module
from logging import getLogger
from pathlib import Path
from pkg_resources import iter_entry_points

from cryptography.fernet import Fernet
from django.core.exceptions import ImproperlyConfigured
from django.db import connection

from pulpcore import constants

# Build paths inside the project like this: BASE_DIR / ...
BASE_DIR = Path(__file__).absolute().parent

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/3.2/howto/deployment/checklist/

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False

ALLOWED_HOSTS = ["*"]

DEPLOY_ROOT = Path("/var/lib/pulp")
MEDIA_ROOT = str(DEPLOY_ROOT / "media")  # Django 3.1 adds support for pathlib.Path

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/3.2/howto/static-files/

STATIC_URL = "/assets/"
STATIC_ROOT = DEPLOY_ROOT / STATIC_URL.strip("/")

DEFAULT_FILE_STORAGE = "pulpcore.app.models.storage.FileSystem"
REDIRECT_TO_OBJECT_STORAGE = True

WORKING_DIRECTORY = DEPLOY_ROOT / "tmp"
FILE_UPLOAD_TEMP_DIR = WORKING_DIRECTORY

CHUNKED_UPLOAD_DIR = "upload"

# List of upload handler classes to be applied in order.
FILE_UPLOAD_HANDLERS = ("pulpcore.app.files.HashingFileUploadHandler",)

SECRET_KEY = True

# Key used to encrypt fields in the database
DB_ENCRYPTION_KEY = "/etc/pulp/certs/database_fields.symmetric.key"

# API Root
API_ROOT = "/pulp/"

# Application definition

INSTALLED_APPS = [
    # django stuff
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "import_export",
    # third-party
    "django_filters",
    "django_guid",
    "drf_spectacular",
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
    "django_guid.middleware.guid_middleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "pulpcore.middleware.DomainMiddleware",
]

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "pulpcore.backends.ObjectRolePermissionBackend",
]

ROOT_URLCONF = "pulpcore.app.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
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
    "DEFAULT_FILTER_BACKENDS": ("pulpcore.filters.PulpFilterBackend",),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.LimitOffsetPagination",
    "PAGE_SIZE": 100,
    "DEFAULT_PERMISSION_CLASSES": ("pulpcore.plugin.access_policy.AccessPolicyFromDB",),
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework.authentication.BasicAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
    "UPLOADED_FILES_USE_URL": False,
    "DEFAULT_VERSIONING_CLASS": "rest_framework.versioning.URLPathVersioning",
    "DEFAULT_SCHEMA_CLASS": "pulpcore.openapi.PulpAutoSchema",
}

# Password validation
# https://docs.djangoproject.com/en/3.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# Internationalization
# https://docs.djangoproject.com/en/3.2/topics/i18n/

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = "USE_I18N", True

USE_L10N = True

USE_TZ = True


# A set of default settings to use if the configuration file in
# /etc/pulp/ is missing or if it does not have values for every setting

# https://docs.djangoproject.com/en/3.2/ref/settings/#databases
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "pulp",
        "USER": "pulp",
        "CONN_MAX_AGE": 0,
    },
}

# Redis default config
REDIS_URL = None
REDIS_HOST = None
REDIS_PORT = None
REDIS_DB = 0
REDIS_PASSWORD = None
REDIS_SSL = False
REDIS_SSL_CA_CERTS = None

# https://docs.djangoproject.com/en/3.2/ref/settings/#logging and
# https://docs.python.org/3/library/logging.config.html
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"format": "pulp [%(correlation_id)s]: %(name)s:%(levelname)s: %(message)s"}
    },
    "filters": {"correlation_id": {"()": "django_guid.log_filters.CorrelationId"}},
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
            "filters": ["correlation_id"],
        }
    },
    "loggers": {
        "": {
            # The root logger
            "handlers": ["console"],
            "level": "INFO",
            "filters": ["correlation_id"],
        },
        "django_guid": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
    },
}

DRF_ACCESS_POLICY = {"reusable_conditions": ["pulpcore.app.global_access_conditions"]}

CONTENT_PATH_PREFIX = "/pulp/content/"
CONTENT_APP_TTL = 30

WORKER_TTL = 30

# how long to protect ephemeral items in minutes
ORPHAN_PROTECTION_TIME = 24 * 60
UPLOAD_PROTECTION_TIME = 0
TMPFILE_PROTECTION_TIME = 0

REMOTE_USER_ENVIRON_NAME = "REMOTE_USER"

ALLOWED_IMPORT_PATHS = []

ALLOWED_EXPORT_PATHS = []

# https://docs.pulpproject.org/pulpcore/configuration/settings.html#pulp-cache
CACHE_ENABLED = False
CACHE_SETTINGS = {
    "EXPIRES_TTL": 600,  # 10 minutes
}

SPECTACULAR_SETTINGS = {
    "SERVE_URLCONF": ROOT_URLCONF,
    "DEFAULT_GENERATOR_CLASS": "pulpcore.openapi.PulpSchemaGenerator",
    "DEFAULT_SCHEMA_CLASS": "pulpcore.openapi.PulpAutoSchema",
    "ENUM_ADD_EXPLICIT_BLANK_NULL_CHOICE": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "COMPONENT_NO_READ_ONLY_REQUIRED": True,
    "GENERIC_ADDITIONAL_PROPERTIES": None,
    "DISABLE_ERRORS_AND_WARNINGS": not DEBUG,
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
ALLOWED_CONTENT_CHECKSUMS = ["sha224", "sha256", "sha384", "sha512"]

DEFAULT_AUTO_FIELD = "django.db.models.AutoField"

TASK_DIAGNOSTICS = False

ANALYTICS = True

HIDE_GUARDED_DISTRIBUTIONS = False

DOMAIN_ENABLED = False

SHELL_PLUS_IMPORTS = [
    "from pulpcore.app.util import get_domain, get_domain_pk, set_domain, get_url, extract_pk",
    "from pulpcore.tasking.tasks import dispatch",
    "from pulpcore.tasking.util import cancel_task",
]

# HERE STARTS DYNACONF EXTENSION LOAD (Keep at the very bottom of settings.py)
# Read more at https://dynaconf.readthedocs.io/en/latest/guides/django.html
from dynaconf import DjangoDynaconf, Validator  # noqa

# Validators
content_origin_validator = Validator(
    "CONTENT_ORIGIN",
    must_exist=True,
    messages={
        "must_exist_true": (
            "CONTENT_ORIGIN is a required setting but it was not configured. This may be caused "
            "by invalid read permissions of the settings file. Note that CONTENT_ORIGIN is set by "
            "the installation automatically."
        )
    },
)
storage_validator = (
    Validator("REDIRECT_TO_OBJECT_STORAGE", eq=False)
    | Validator("DEFAULT_FILE_STORAGE", eq="pulpcore.app.models.storage.FileSystem")
    | Validator("DEFAULT_FILE_STORAGE", eq="storages.backends.azure_storage.AzureStorage")
    | Validator("DEFAULT_FILE_STORAGE", eq="storages.backends.s3boto3.S3Boto3Storage")
    | Validator("DEFAULT_FILE_STORAGE", eq="storages.backends.gcloud.GoogleCloudStorage")
)
storage_validator.messages["combined"] = (
    "'REDIRECT_TO_OBJECT_STORAGE=True' is only supported with the local file, S3, GCP or Azure"
    "storage backend configured in DEFAULT_FILE_STORAGE."
)

cache_enabled_validator = Validator("CACHE_ENABLED", eq=True)
redis_url_validator = Validator("REDIS_URL", must_exist=True, when=cache_enabled_validator)
redis_host_validator = Validator("REDIS_HOST", must_exist=True, when=cache_enabled_validator)
redis_port_validator = Validator("REDIS_PORT", must_exist=True, when=cache_enabled_validator)
cache_validator = redis_url_validator | (redis_host_validator & redis_port_validator)
cache_validator.messages["combined"] = (
    "CACHE_ENABLED is enabled but it requires to have REDIS configured. Please check "
    "https://docs.pulpproject.org/pulpcore/configuration/settings.html#redis-settings "
    "for more information."
)

sha256_validator = Validator(
    "ALLOWED_CONTENT_CHECKSUMS",
    cont="sha256",
    messages={
        "operations": "ALLOWED_CONTENT_CHECKSUMS MUST contain 'sha256' - Pulp's "
        "content addressable storage relies on sha256 to identify entities."
    },
)

unknown_algs_validator = Validator(
    "ALLOWED_CONTENT_CHECKSUMS",
    condition=lambda x: len(set(x).difference(constants.ALL_KNOWN_CONTENT_CHECKSUMS)) == 0,
    messages={
        "condition": (
            "ALLOWED_CONTENT_CHECKSUMS may only contain algorithms known to pulp - see "
            "constants.ALL_KNOWN_CONTENT_CHECKSUMS for the allowed list."
        )
    },
)

api_root_validator = Validator(
    "API_ROOT",
    condition=lambda x: x.startswith("/") and x.endswith("/"),
    messages={
        "condition": ("The API_ROOT must start and end with a '/', currently it is '{value}'")
    },
)


settings = DjangoDynaconf(
    __name__,
    ENVVAR_PREFIX_FOR_DYNACONF="PULP",
    ENV_SWITCHER_FOR_DYNACONF="PULP_ENV",
    PRELOAD_FOR_DYNACONF=[
        "{}.app.settings".format(plugin_name) for plugin_name in INSTALLED_PULP_PLUGINS
    ],
    ENVVAR_FOR_DYNACONF="PULP_SETTINGS",
    load_dotenv=False,
    validators=[
        api_root_validator,
        cache_validator,
        content_origin_validator,
        sha256_validator,
        storage_validator,
        unknown_algs_validator,
    ],
)
# HERE ENDS DYNACONF EXTENSION LOAD (No more code below this line)

_logger = getLogger(__name__)


if not (
    Path(sys.argv[0]).name == "pytest"
    or Path(sys.argv[0]).name == "sphinx-build"
    or (len(sys.argv) >= 2 and sys.argv[1] == "collectstatic")
):
    try:
        with open(DB_ENCRYPTION_KEY, "rb") as key_file:
            Fernet(key_file.read())
    except Exception as ex:
        raise ImproperlyConfigured(
            ("Could not load DB_ENCRYPTION_KEY file '{file}': {err}").format(
                file=DB_ENCRYPTION_KEY, err=ex
            )
        )


FORBIDDEN_CHECKSUMS = set(constants.ALL_KNOWN_CONTENT_CHECKSUMS).difference(
    ALLOWED_CONTENT_CHECKSUMS
)

_SKIPPED_COMMANDS_FOR_CONTENT_CHECKS = ["handle-artifact-checksums", "migrate", "collectstatic"]

if not (len(sys.argv) >= 2 and sys.argv[1] in _SKIPPED_COMMANDS_FOR_CONTENT_CHECKS):
    try:
        with connection.cursor() as cursor:
            for checksum in ALLOWED_CONTENT_CHECKSUMS:
                # can't import Artifact here so use a direct db connection
                cursor.execute(f"SELECT count(pulp_id) FROM core_artifact WHERE {checksum} IS NULL")
                row = cursor.fetchone()
                if row[0] > 0:
                    raise ImproperlyConfigured(
                        (
                            "There have been identified artifacts missing checksum '{}'. "
                            "Run 'pulpcore-manager handle-artifact-checksums' first to populate "
                            "missing artifact checksums."
                        ).format(checksum)
                    )
            for checksum in FORBIDDEN_CHECKSUMS:
                # can't import Artifact here so use a direct db connection
                cursor.execute(
                    f"SELECT count(pulp_id) FROM core_artifact WHERE {checksum} IS NOT NULL"
                )
                row = cursor.fetchone()
                if row[0] > 0:
                    raise ImproperlyConfigured(
                        (
                            "There have been identified artifacts with forbidden checksum '{}'. "
                            "Run 'pulpcore-manager handle-artifact-checksums' first to unset "
                            "forbidden checksums."
                        ).format(checksum)
                    )

            # warn if there are remote artifacts with checksums but no allowed checksums
            cond = " AND ".join([f"{c} IS NULL" for c in constants.ALL_KNOWN_CONTENT_CHECKSUMS])
            no_checksum_query = f"SELECT pulp_id FROM core_remoteartifact WHERE {cond}"
            cond = " AND ".join([f"{c} IS NULL" for c in ALLOWED_CONTENT_CHECKSUMS])
            cursor.execute(
                f"SELECT count(pulp_id) FROM core_remoteartifact WHERE {cond} AND "
                f"pulp_id NOT IN ({no_checksum_query})"
            )
            row = cursor.fetchone()
            if row[0] > 0:
                _logger.warning(
                    (
                        "Warning: detected remote content without allowed checksums. "
                        "Run 'pulpcore-manager handle-artifact-checksums --report' to "
                        "view this content."
                    )
                )

    except ImproperlyConfigured as e:
        raise e
    except Exception:
        # our check could fail if the table hasn't been created yet or we can't get a db connection
        pass
    finally:
        connection.close()

settings.set("V3_API_ROOT", settings.API_ROOT + "api/v3/")  # Not user configurable
settings.set("V3_DOMAIN_API_ROOT", settings.API_ROOT + "<slug:pulp_domain>/api/v3/")
settings.set("V3_API_ROOT_NO_FRONT_SLASH", settings.V3_API_ROOT.lstrip("/"))
settings.set("V3_DOMAIN_API_ROOT_NO_FRONT_SLASH", settings.V3_DOMAIN_API_ROOT.lstrip("/"))
