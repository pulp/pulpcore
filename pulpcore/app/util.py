import hashlib
import zlib
import os
import socket
import tempfile
import gnupg

from functools import lru_cache
from gettext import gettext as _
from urllib.parse import urlparse
from contextlib import ExitStack
from contextvars import ContextVar
from datetime import timedelta
from uuid import UUID

from django.apps import apps
from django.conf import settings
from django.db import connection
from django.db.models import Model, UUIDField
from django.urls import Resolver404, resolve

from rest_framework.serializers import ValidationError
from rest_framework.reverse import reverse as drf_reverse

from pulpcore.app.loggers import deprecation_logger
from pulpcore.app.apps import pulp_plugin_configs
from pulpcore.app import models
from pulpcore.exceptions import AdvisoryLockError
from pulpcore.exceptions.validation import InvalidSignatureError


# a little cache so viewset_for_model doesn't have to iterate over every app every time
_model_viewset_cache = {}
STRIPPED_API_ROOT = settings.API_ROOT.strip("/")


def reverse(viewname, args=None, kwargs=None, request=None, relative_url=True, **extra):
    """
    Customized reverse to handle Pulp specific parameters like domains and API_ROOT rewrite.

    Calls DRF's reverse, but with request as None if relative_url is True (default) so that the
    returned url is always relative.
    """
    kwargs = kwargs or {}
    if settings.DOMAIN_ENABLED:
        kwargs.setdefault("pulp_domain", get_domain().name)
    if settings.API_ROOT_REWRITE_HEADER:
        kwargs.setdefault("api_root", getattr(request, "api_root", STRIPPED_API_ROOT))
    if relative_url:
        request = None
    return drf_reverse(viewname, args=args, kwargs=kwargs, request=request, **extra)


def get_url(model, domain=None, request=None):
    """
    Get a resource url for the specified model instance or class. This returns the path component of
    the resource URI.

    Args:
        model (django.models.Model): A model instance or class.
        domain Optional(str or Domain): The domain the url should be in if DOMAIN_ENABLED is set and
        domain can not be gathered from the model. Defaults to 'default'.
        request Optional(django.http.HttpRequest): The request object this url is being created for.

    Returns:
        str: The path component of the resource url
    """
    kwargs = {}
    view_action = "list"
    if settings.DOMAIN_ENABLED:
        kwargs["pulp_domain"] = "default"
        if not domain and hasattr(model, "pulp_domain") and isinstance(model, model._meta.model):
            kwargs["pulp_domain"] = model.pulp_domain.name
        elif isinstance(domain, models.Domain):
            kwargs["pulp_domain"] = domain.name
        elif isinstance(domain, str):
            kwargs["pulp_domain"] = domain
    if isinstance(model, model._meta.model):
        view_action = "detail"
        kwargs["pk"] = model.pk

    return reverse(get_view_name_for_model(model, view_action), kwargs=kwargs, request=request)


def get_prn(instance=None, uri=None):
    """
    Get a Pulp Resource Name (PRN) for the specified model instance. It is similar to a HREF
    url in that it uniquely identifies a resource, but it also has the guarantee that it will not
    change regardless of API_ROOT or DOMAIN_ENABLED. This is used in our resource locking/
    reservation code to identify resources.

    The format for the PRN is as follows:
    ```
        prn:model-label-lower:pk
    ```

    Examples:
        instance=FileRepository(pk=123) -> prn:file.filerepository:123
        instance=Artifact(pk=abc) -> prn:core.artifact:abc
        uri=/rerouted/api/v3/repositories/rpm/rpm/123/versions/2/ -> prn:core.repositoryversion:abc
        uri=/pulp/foodomain/api/v3/content/ansible/role/123/ -> prn:ansible.role:123

    Args:
        instance Optional(django.models.Model): A model instance.
        uri Optional(str): A resource URI

    Returns:
        prn (str): The PRN of the passed in resource
    """
    if uri:
        from pulpcore.app.viewsets import NamedModelViewSet

        instance = NamedModelViewSet.get_resource(uri)

    if not isinstance(instance, Model):
        raise ValidationError(_("instance({}) must be a Model").format(instance))

    if isinstance(instance, models.MasterModel):
        instance = instance.cast()

    return f"prn:{instance._meta.label_lower}:{instance.pk}"


def resolve_prn(prn):
    """
    Resolve a PRN to its model and pk.

    Args:
        prn (str): The PRN to resolve.

    Returns:
        model_pk_tuple (tuple): A tuple of the model class and pk of the PRN

    Raises:
        rest_framework.exceptions.ValidationError: on invalid PRN.
    """
    if not prn.startswith("prn:"):
        raise ValidationError(_("PRN must start with 'prn:': {}").format(prn))
    split = prn.split(":")
    if len(split) != 3:
        raise ValidationError(
            _("PRN must be of the form 'prn:app_label.model_label:pk': {}").format(prn)
        )
    p, full_model_label, pk = split
    try:
        model = apps.get_model(full_model_label)
    except LookupError:
        raise ValidationError(_("Model {} does not exist").format(full_model_label))
    except ValueError:
        raise ValidationError(
            _("The model must be in the form of 'app_label.model_label': {}").format(
                full_model_label
            )
        )
    if isinstance(model._meta.pk, UUIDField):
        try:
            UUID(pk, version=4)
        except ValueError:
            raise ValidationError(_("PK invalid: {}").format(pk))

    return model, pk


def extract_pk(uri, only_prn=False):
    """
    Resolve a resource URI or PRN to a simple PK value.

    Provides a means to resolve an href/prn passed in a POST body to a primary key.
    Doesn't assume anything about whether the resource corresponding to the URI/PRN
    passed in actually exists.

    Note:
        Cannot be used with nested URIs where the PK of the final resource is not present.
        e.g. RepositoryVersion URI consists of repository PK and version number - no
        RepositoryVersion PK is present within the URI.

    Args:
        uri (str): A resource URI/PRN.
        only_prn (bool): Ensure passed in value is only a valid PRN

    Returns:
        primary_key (uuid.uuid4): The primary key of the resource extracted from the URI/PRN.

    Raises:
        rest_framework.exceptions.ValidationError: on invalid URI/PRN.
    """
    if uri.startswith("prn:"):
        prn = uri.split(":")
        if len(prn) != 3:
            raise ValidationError(_("PRN not valid: {p}").format(p=prn))
        return prn[2]
    elif only_prn:
        raise ValidationError(_("Not a valid PRN: {p}, must start with 'prn:'").format(p=uri))
    try:
        match = resolve(urlparse(uri).path)
    except Resolver404:
        raise ValidationError(detail=_("URI not valid: {u}").format(u=uri))

    try:
        return match.kwargs["pk"]
    except KeyError:
        raise ValidationError("URI does not contain an unqualified resource PK")


def raise_for_unknown_content_units(
    existing_content_units,
    content_units_pks_hrefs,
    domain=None,
):
    """Verify if all the specified content units were found in the database.

    Args:
        existing_content_units (pulpcore.plugin.models.Content): Content filtered by
            specified_content_units.
        content_units_pks_hrefs (dict): An original dictionary of pk-href pairs that
            are used for the verification.
        domain (pulpcore.plugin.models.Domain): A domain to use for verifying that all the
            content units are within the same domain. defaults to current domain.
    Raises:
        ValidationError: If some of the referenced content units are not present in the database or
            content units are from multiple domains
    """
    domain = domain or get_domain()
    bad_domain_pks = existing_content_units.exclude(pulp_domain=domain).values_list("pk", flat=True)
    if bad_domain_pks:
        bad_hrefs = [content_units_pks_hrefs[str(pk)] for pk in bad_domain_pks]
        raise ValidationError(
            _("Content units are not a part of the current domain {}: {}").format(
                domain.name, bad_hrefs
            )
        )

    existing_content_units_pks = existing_content_units.values_list("pk", flat=True)
    existing_content_units_pks = set(map(str, existing_content_units_pks))

    missing_pks = set(content_units_pks_hrefs.keys()) - existing_content_units_pks
    if missing_pks:
        missing_hrefs = [content_units_pks_hrefs[pk] for pk in missing_pks]
        raise ValidationError(
            _("Could not find the following content units: {}").format(missing_hrefs)
        )


# based on their name, viewset_for_model and view_name_for_model look like they should
# live over in the viewsets namespace, but these tools exist for serializers, which are
# depended on by viewsets. They're defined here because they're used here, and to avoid
# odd import dependencies.
def get_viewset_for_model(model_obj, ignore_error=False):
    """
    Given a Model instance or class, return the registered ViewSet for that Model
    """
    # model_obj can be an instance or class, force it to class
    model_class = model_obj._meta.model
    if model_class in _model_viewset_cache:
        return _model_viewset_cache[model_class]

    # cache miss, fill in the cache while we look for our matching viewset
    model_viewset = None
    # go through the viewset registry to find the viewset for the passed-in model
    for app in pulp_plugin_configs():
        for model, viewsets in app.named_viewsets.items():
            # There may be multiple viewsets for a model. In this
            # case, we can't reverse the mapping.
            if len(viewsets) == 1:
                viewset = viewsets[0]
                _model_viewset_cache.setdefault(model, viewset)
                if model is model_class:
                    model_viewset = viewset
                    break
        if model_viewset is not None:
            break

    if model_viewset is None:
        if ignore_error:
            return None
        raise LookupError("Could not determine ViewSet base name for model {}".format(model_class))

    return viewset


def get_view_name_for_model(model_obj, view_action):
    """
    Given a Model instance or class, return the correct view name for that ViewSet view.

    This is the "glue" that generates view names dynamically based on a model object.

    Args:
        model_obj (pulpcore.app.models.Model): a Model that should have a ViewSet
        view_action (str): name of the view action as expected by DRF. See their docs for details.

    Returns:
        str: view name for the correct ViewSet

    Raises:
        LookupError: if no ViewSet is found for the Model
    """
    # Import this here to prevent out-of-order plugin discovery
    from pulpcore.app.urls import all_routers

    if isinstance(model_obj, models.MasterModel):
        model_obj = model_obj.cast()
    viewset = get_viewset_for_model(model_obj)

    # return the complete view name, joining the registered viewset base name with
    # the requested view method.
    for router in all_routers:
        for pattern, registered_viewset, base_name in router.registry:
            if registered_viewset is viewset:
                return "-".join((base_name, view_action))
    raise LookupError(f"{viewset} view not found")


def batch_qs(qs, batch_size=1000):
    """Returns a queryset batch from the given queryset.

    Make sure to order the queryset.

    Args:
       qs: The queryset we want to iterate over in batches.
       batch_size: Defaults to 1000.

    Example:
        To iterate over a queryset while retrieving records from the DB in batches, use::

            article_qs = Article.objects.order_by('id')
            for qs in batch_qs(article_qs):
                for article in qs:
                    print article.body
    """
    total = qs.count()
    for start in range(0, total, batch_size):
        end = min(start + batch_size, total)
        yield qs[start:end]


def get_view_urlpattern(view):
    """
    Get a full urlpattern for a view which includes a parent urlpattern if it exists.
    E.g. for repository versions the urlpattern is just `versions` without its parent_viewset
    urlpattern.

    Args:
        view(subclass rest_framework.viewsets.GenericViewSet): The view being requested.

    Returns:
        str: a full urlpattern for a specified view/viewset
    """
    if hasattr(view, "parent_viewset") and view.parent_viewset:
        return os.path.join(view.parent_viewset.urlpattern(), view.urlpattern())
    return view.urlpattern()


def get_request_without_query_params(context):
    """
    Remove query parameters from a request object.

    Removing query parameters should not influence the features provided by the library
    'djangorestframework-queryfields'. But, once a user selects which fields should be sent in the
    API response, any other fields are going to be filtered out even though they are still required
    for serialization purposes in the future.

    Some serializers need to be aware of the context that triggered the operation. For example, when
    a Task is serialized, created resources need to be serialized as well. Missing context lead to
    invalid serialization if the created resources do not have knowledge about the initial request.

    This method modifies the request object in-place, meaning that all other objects that reference
    this object may be affected.

    Args:
        context (dict): A context containing the request object.

    Returns:
        rest_framework.request.Request: a request object without query parameters
    """
    request = context.get("request")

    if request is not None:
        request.query_params._mutable = True
        request.query_params.clear()
        request.query_params._mutable = False

    return request


def gpg_verify(public_keys, signature, detached_data=None):
    """
    Check whether the provided gnupg signature is valid for one of the provided public keys.

    Args:
        public_keys (str): Ascii armored public key data
        signature (str, file-like, Artifact): The signature data as a path or as a file-like object
        detached_data (str) [optional]: The filesystem path to signed data in case of a detached
            signature

    Returns:
        gnupg.Verify: The result of the verification

    Raises:
        pulpcore.exceptions.validation.InvalidSignatureError: In case the signature is invalid.
    """
    with tempfile.TemporaryDirectory(dir=settings.WORKING_DIRECTORY) as temp_directory_name:
        gpg = gnupg.GPG(gnupghome=temp_directory_name)
        gpg.import_keys(public_keys)

        with ExitStack() as stack:
            if isinstance(signature, str):
                signature = stack.enter_context(open(signature, "rb"))
            elif isinstance(signature, models.Artifact):
                signature = stack.enter_context(signature.file)

            verified = gpg.verify_file(signature, detached_data)
        if not verified.valid:
            raise InvalidSignatureError(_("The signature is not valid."), verified=verified)
    return verified


def compute_file_hash(filename, hasher=None, cumulative_hash=None, blocksize=8192):
    if hasher is None:
        hasher = hashlib.sha256()

    with open(filename, "rb") as f:
        # Read and update hash string value in blocks of 8K
        while chunk := f.read(blocksize):
            hasher.update(chunk)
            if cumulative_hash:
                cumulative_hash.update(chunk)
        return hasher.hexdigest()


class Crc32Hasher:
    """Wrapper to make the CRC32 implementation act like a standard hashlib hasher"""

    def __init__(self):
        self.hashval = 0

    def update(self, data):
        self.hashval = zlib.crc32(data, self.hashval)

    def digest(self):
        return str(self.hashval)

    def hexdigest(self):
        return hex(self.hashval)[2:]


def configure_analytics():
    task_name = "pulpcore.app.tasks.analytics.post_analytics"
    dispatch_interval = timedelta(days=1)
    name = "Post Anonymous Analytics Periodically"
    analytics = settings.ANALYTICS
    if settings.get("TELEMETRY") is not None:
        deprecation_logger.warning("TELEMETRY setting is deprecated. Use ANALYTICS.")
        analytics = settings.TELEMETRY
    if analytics:
        models.TaskSchedule.objects.update_or_create(
            name=name, defaults={"task_name": task_name, "dispatch_interval": dispatch_interval}
        )
    else:
        models.TaskSchedule.objects.filter(task_name=task_name).delete()


def configure_cleanup():
    for name, task_name, protection_time in [
        ("uploads", "pulpcore.app.tasks.orphan.upload_cleanup", settings.UPLOAD_PROTECTION_TIME),
        (
            "shared temporary files",
            "pulpcore.app.tasks.orphan.tmpfile_cleanup",
            settings.TMPFILE_PROTECTION_TIME,
        ),
        ("tasks", "pulpcore.app.tasks.purge.purge", settings.TASK_PROTECTION_TIME),
    ]:
        if protection_time > 0:
            dispatch_interval = timedelta(minutes=protection_time)
            name = f"Clean up stale {name} periodically"
            models.TaskSchedule.objects.update_or_create(
                name=name, defaults={"task_name": task_name, "dispatch_interval": dispatch_interval}
            )
        else:
            models.TaskSchedule.objects.filter(task_name=task_name).delete()


def configure_periodic_telemetry():
    task_name = "pulpcore.app.tasks.telemetry.otel_metrics"
    dispatch_interval = timedelta(minutes=5)
    name = "Emit OpenTelemetry metrics periodically"

    if settings.OTEL_ENABLED and settings.DOMAIN_ENABLED:
        models.TaskSchedule.objects.update_or_create(
            name=name, defaults={"task_name": task_name, "dispatch_interval": dispatch_interval}
        )
    else:
        models.TaskSchedule.objects.filter(task_name=task_name).delete()


@lru_cache(maxsize=1)
def _artifact_serving_distribution():
    return models.ArtifactDistribution.objects.get()


def get_artifact_url(artifact, headers=None, http_method=None):
    """Get artifact url.

    Plugins can use this method to generate a pre-authenticated URL to the artifact in the
    configured storage backend. This can be used to facilitate external services for validation of
    the content.

    This method will generate redirect links to the configured external object storage, or to the
    special "artifact redirect" distribution in the content-app top serve from the local filesystem
    or private cloud storage.
    """
    artifact_file = artifact.file
    content_disposition = f"attachment;filename={artifact.pk}"
    artifact_domain = artifact.pulp_domain
    if (
        artifact_domain.storage_class == "pulpcore.app.models.storage.FileSystem"
        or not artifact_domain.redirect_to_object_storage
    ):
        return _artifact_serving_distribution().artifact_url(artifact)
    elif artifact_domain.storage_class == "storages.backends.s3boto3.S3Boto3Storage":
        parameters = {"ResponseContentDisposition": content_disposition}
        if headers and headers.get("Content-Type"):
            parameters["ResponseContentType"] = headers.get("Content-Type")
        url = artifact_file.storage.url(
            artifact_file.name, parameters=parameters, http_method=http_method
        )
    elif artifact_domain.storage_class == "storages.backends.azure_storage.AzureStorage":
        parameters = {"content_disposition": content_disposition}
        if headers and headers.get("Content-Type"):
            parameters["content_type"] = headers.get("Content-Type")
        url = artifact_file.storage.url(artifact_file.name, parameters=parameters)
    elif artifact_domain.storage_class == "storages.backends.gcloud.GoogleCloudStorage":
        parameters = {"response_disposition": content_disposition}
        if headers and headers.get("Content-Type"):
            parameters["content_type"] = headers.get("Content-Type")
        url = artifact_file.storage.url(artifact_file.name, parameters=parameters)
    else:
        if settings.DOMAIN_ENABLED:
            loc = f"domain {artifact_domain.name}.storage_class"
        else:
            loc = "settings.STORAGES['default']['BACKEND']"

        raise NotImplementedError(
            f"The value {loc}={artifact_domain.storage_class} does not allow redirecting."
        )
    return url


current_task = ContextVar("current_task", default=None)
_current_user_func = ContextVar("current_user", default=lambda: None)


def get_current_user():
    return _current_user_func.get()()


def get_current_authenticated_user():
    user = get_current_user()
    return user if (user is not None and user.is_authenticated) else None


def set_current_user(user):
    _current_user_func.set(lambda: user)


def set_current_user_lazy(user_func):
    # This allows to be lazy, because the authentication happens on the view and not in the
    # middleware.
    _current_user_func.set(user_func)


default_domain = None
current_domain = ContextVar("current_domain", default=None)


def get_default_domain():
    global default_domain
    # This will run in a post-migration hook
    if default_domain is None:
        try:
            Domain = models.Domain
        except AttributeError:
            return None
        try:
            default_domain = Domain.objects.get(name="default")
        except Domain.DoesNotExist:
            default_domain = Domain(
                name="default", storage_class=settings.STORAGES["default"]["BACKEND"]
            )
            default_domain.save(skip_hooks=True)

    return default_domain


def get_domain():
    return current_domain.get() or get_default_domain()


def get_domain_pk():
    """
    THIS CAN/WILL BE RAN IN MIGRATIONS. DO NOT USE ORM FOR IT MIGHT GENERATE INVALID SQL.

    This is ran in plugin migrations so we can not move this implemenation or change its
    semantics, EVER!
    """
    if domain := current_domain.get():
        return domain.pk
    # Same behavior as get_domain: use currently set domain, else assume default domain
    if default_domain:
        return default_domain.pk
    # If we haven't cached the default_domain then use raw SQL to get its PK
    with connection.cursor() as cursor:
        cursor.execute("SELECT pulp_id FROM core_domain WHERE name = 'default'")
        row = cursor.fetchone()
        return row[0]


def set_domain(new_domain):
    current_domain.set(new_domain)
    return new_domain


def cache_key(base_path):
    """Returns the base-key(s) used in the Cache for the passed base_path(s)."""
    if settings.DOMAIN_ENABLED:
        domain = get_domain()
        if isinstance(base_path, str):
            base_path = f"{domain.name}:{base_path}"
        else:
            base_path = [f"{domain.name}:{path}" for path in base_path]

    return base_path


@lru_cache(maxsize=1)
def get_worker_name():
    return f"{os.getpid()}@{socket.gethostname()}"


class PGAdvisoryLock:
    """
    A context manager that will hold a postgres advisory lock non-blocking.

    The locks can be chosen from a lock group to avoid collisions. They will never collide with the
    locks used for tasks.
    """

    def __init__(self, lock, lock_group=0):
        self.lock_group = lock_group
        self.lock = lock

    def __enter__(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s, %s)", [self.lock_group, self.lock])
            acquired = cursor.fetchone()[0]
        if not acquired:
            raise AdvisoryLockError("Could not acquire lock.")
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s, %s)", [self.lock_group, self.lock])
            released = cursor.fetchone()[0]
        if not released:
            raise RuntimeError("Lock not held.")


def normalize_http_status(status):
    """Convert the HTTP status code to 2xx, 3xx, etc., normalizing the last two digits."""
    if 100 <= status < 200:
        return "1xx"
    elif 200 <= status < 300:
        return "2xx"
    elif 300 <= status < 400:
        return "3xx"
    elif 400 <= status < 500:
        return "4xx"
    elif 500 <= status < 600:
        return "5xx"
    else:
        return ""
