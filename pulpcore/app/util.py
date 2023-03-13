from functools import lru_cache
from gettext import gettext as _
import os
import tempfile

from urllib.parse import urlparse

from contextlib import ExitStack
from contextvars import ContextVar
from datetime import timedelta
import gnupg

from django.conf import settings
from django.apps import apps
from django.urls import Resolver404, resolve, reverse
from django.contrib.contenttypes.models import ContentType
from pkg_resources import get_distribution
from rest_framework.serializers import ValidationError

from pulpcore.app.loggers import deprecation_logger
from pulpcore.app.apps import pulp_plugin_configs
from pulpcore.app import models
from pulpcore.exceptions.validation import InvalidSignatureError

# a little cache so viewset_for_model doesn't have to iterate over every app every time
_model_viewset_cache = {}


def get_url(model, domain=None):
    """
    Get a resource url for the specified model instance or class. This returns the path component of
    the resource URI.  This is used in our resource locking/reservation code to identify resources.

    Args:
        model (django.models.Model): A model instance or class.
        domain Optional(str or Domain): The domain the url should be in if DOMAIN_ENABLED is set and
        domain can not be gathered from the model. Defaults to 'default'.

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

    return reverse(get_view_name_for_model(model, view_action), kwargs=kwargs)


def extract_pk(uri):
    """
    Resolve a resource URI to a simple PK value.

    Provides a means to resolve an href passed in a POST body to a primary key.
    Doesn't assume anything about whether the resource corresponding to the URI
    passed in actually exists.

    Note:
        Cannot be used with nested URIs where the PK of the final resource is not present.
        e.g. RepositoryVersion URI consists of repository PK and version number - no
        RepositoryVersion PK is present within the URI.

    Args:
        uri (str): A resource URI.

    Returns:
        primary_key (uuid.uuid4): The primary key of the resource extracted from the URI.

    Raises:
        rest_framework.exceptions.ValidationError: on invalid URI.
    """
    try:
        match = resolve(urlparse(uri).path)
    except Resolver404:
        raise ValidationError(detail=_("URI not valid: {u}").format(u=uri))

    try:
        return match.kwargs["pk"]
    except KeyError:
        raise ValidationError("URI does not contain an unqualified resource PK")


def raise_for_unknown_content_units(existing_content_units, content_units_pks_hrefs):
    """Verify if all the specified content units were found in the database.

    Args:
        existing_content_units (pulpcore.plugin.models.Content): Content filtered by
            specified_content_units.
        content_units_pks_hrefs (dict): An original dictionary of pk-href pairs that
            are used for the verification.
    Raises:
        ValidationError: If some of the referenced content units are not present in the database
    """
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
    raise LookupError("view not found")


def batch_qs(qs, batch_size=1000):
    """
    Returns a queryset batch in the given queryset.

    Usage:
        # Make sure to order your querset
        article_qs = Article.objects.order_by('id')
        for qs in batch_qs(article_qs):
            for article in qs:
                print article.body
    """
    total = qs.count()
    for start in range(0, total, batch_size):
        end = min(start + batch_size, total)
        yield qs[start:end]


def get_version_from_model(in_model):
    """
    Return a tuple (dist-label, version) for the distribution that 'owns' the model

    Args:
        in_model (models.Model): model whose owning-plugin-version we need

    Returns:
        (str, str): tuple containing owning-plugin's (distribution, version)
    """
    app_label = ContentType.objects.get_for_model(in_model, for_concrete_model=False).app_label
    app_config_module = apps.get_app_config(app_label).name
    maybe_the_distribution_name = app_config_module.split(".")[0]
    version = get_distribution(maybe_the_distribution_name).version  # hope for the best!
    return maybe_the_distribution_name, version


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


def verify_signature(filepath, public_key, detached_data=None):
    """
    Check whether the provided file can be verified with the particular public key.

    When dealing with a detached signature (referenced by the 'filepath' argument), one have to pass
    the reference to a data file that was signed by that signature.
    """
    deprecation_logger.warning(
        "verify_signature() is deprecated and will be removed in pulpcore==3.25; use gpg_verify()."
    )

    with tempfile.TemporaryDirectory(dir=settings.WORKING_DIRECTORY) as temp_directory_name:
        gpg = gnupg.GPG(gnupghome=temp_directory_name)
        gpg.import_keys(public_key)
        imported_keys = gpg.list_keys()

        if len(imported_keys) != 1:
            raise RuntimeError("Exactly one key must be imported.")

        with open(filepath, "rb") as signature:
            verified = gpg.verify_file(signature, detached_data)
            if not verified.valid:
                raise InvalidSignatureError(
                    f"The file '{filepath}' does not contain a valid signature."
                )


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
            loc = "settings.DEFAULT_FILE_STORAGE"

        raise NotImplementedError(
            f"The value {loc}={artifact_domain.storage_class} does not allow redirecting."
        )
    return url


default_domain = None
current_domain = ContextVar("current_domain", default=None)


def get_default_domain():
    global default_domain
    # This can be run in a migration, and once after
    if default_domain is None:
        try:
            Domain = models.Domain
        except AttributeError:
            return None
        try:
            default_domain = Domain.objects.get(name="default")
        except Domain.DoesNotExist:
            default_domain = Domain(name="default", storage_class=settings.DEFAULT_FILE_STORAGE)
            default_domain.save(skip_hooks=True)

    return default_domain


def get_domain():
    return current_domain.get() or get_default_domain()


def get_domain_pk():
    return get_domain().pk


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
