import os

from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from pkg_resources import get_distribution

from pulpcore.app.apps import pulp_plugin_configs
from pulpcore.app import models

# a little cache so viewset_for_model doesn't have iterate over every app every time
_model_viewset_cache = {}


# based on their name, viewset_for_model and view_name_for_model look like they should
# live over in the viewsets namespace, but these tools exist for serializers, which are
# depended on by viewsets. They're defined here because they're used here, and to avoid
# odd import dependencies.
def get_viewset_for_model(model_obj):
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
