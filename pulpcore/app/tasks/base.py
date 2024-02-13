from django.db import transaction

from pulpcore.app.apps import get_plugin_config
from pulpcore.app.models import CreatedResource
from pulpcore.plugin.models import MasterModel


def general_create_from_temp_file(app_label, serializer_name, temp_file_pk, *args, **kwargs):
    """
    Create a model instance from contents stored in a temporary file.

    A task which executes this function takes the ownership of a temporary file and deletes it
    afterwards. This function calls the function general_create() to create a model instance.
    """
    data = kwargs.pop("data", {})
    context = kwargs.pop("context", {})
    context["pulp_temp_file_pk"] = temp_file_pk

    general_create(app_label, serializer_name, data=data, context=context, *args, **kwargs)


def general_create(app_label, serializer_name, *args, **kwargs):
    """
    Create a model instance.

    Raises:
        ValidationError: If the serializer is not valid

    """
    data = kwargs.pop("data", None)
    context = kwargs.pop("context", {})
    serializer_class = get_plugin_config(app_label).named_serializers[serializer_name]
    serializer = serializer_class(data=data, context=context)
    serializer.is_valid(raise_exception=True)
    instance = serializer.save()
    if isinstance(instance, MasterModel):
        instance = instance.cast()
    resource = CreatedResource(content_object=instance)
    resource.save()


def general_update(instance_id, app_label, serializer_name, *args, **kwargs):
    """
    Update a model

    The model instance is identified using the app_label, id, and serializer name. The serializer is
    used to perform validation.

    Args:
        id (str): the id of the model
        app_label (str): the Django app label of the plugin that provides the model
        serializer_name (str): name of the serializer class for the model
        data (dict): dictionary whose keys represent the fields of the model and their corresponding
            values.
        partial (bool): When true, only the fields specified in the data dictionary are updated.
            When false, any fields missing from the data dictionary are assumed to be None and
            their values are updated as such.

    Raises:
        [rest_framework.exceptions.ValidationError][]: When serializer instance can't be saved
            due to validation error. This theoretically should never occur since validation is
            performed before the task is dispatched.
    """
    data = kwargs.pop("data", None)
    partial = kwargs.pop("partial", False)
    serializer_class = get_plugin_config(app_label).named_serializers[serializer_name]
    instance = serializer_class.Meta.model.objects.get(pk=instance_id)
    if isinstance(instance, MasterModel):
        instance = instance.cast()
    serializer = serializer_class(instance, data=data, partial=partial)
    serializer.is_valid(raise_exception=True)
    serializer.save()


def general_delete(instance_id, app_label, serializer_name):
    """
    Delete a model

    The model instance is identified using the app_label, id, and serializer name.

    Args:
        id (str): the id of the model
        app_label (str): the Django app label of the plugin that provides the model
        serializer_name (str): name of the serializer class for the model
    """
    serializer_class = get_plugin_config(app_label).named_serializers[serializer_name]
    instance = serializer_class.Meta.model.objects.get(pk=instance_id)
    if isinstance(instance, MasterModel):
        instance = instance.cast()
    instance.delete()


def general_multi_delete(instance_ids):
    """
    Delete a list of model instances in a transaction

    The model instances are identified using the id, app_label, and serializer_name.

    Args:
        instance_ids (list): List of tupels of id, app_label, serializer_name
    """
    instances = []
    for instance_id, app_label, serializer_name in instance_ids:
        serializer_class = get_plugin_config(app_label).named_serializers[serializer_name]
        instance = serializer_class.Meta.model.objects.get(pk=instance_id)
        if isinstance(instance, MasterModel):
            instance = instance.cast()
        instances.append(instance)
    with transaction.atomic():
        for instance in instances:
            instance.delete()


def generic_cascade_delete_task(instance_id, app_label, serializer_name):
    """
    Delete a model

    The model instance is identified using the app_label, id, and serializer name.

    Args:
        id (str): the id of the model
        app_label (str): the Django app label of the plugin that provides the model
        serializer_name (str): name of the serializer class for the model
    """
    from pulpcore.app.apps import get_plugin_config
    from pulpcore.app.django_util import cascade_delete

    serializer_class = get_plugin_config(app_label).named_serializers[serializer_name]
    instance = serializer_class.Meta.model.objects.get(pk=instance_id)
    if isinstance(instance, MasterModel):
        instance = instance.cast()

    # The purpose is to avoid the memory spike caused by the deletion of an object at the apex
    # of a large tree of cascading deletes. As per the Django documentation [0], cascading
    # deletes are handled by Django and require objects to be loaded into memory. If the tree
    # of objects is sufficiently large, this can result in a fatal memory spike.
    # [0] https://docs.djangoproject.com/en/4.2/ref/models/querysets/#delete
    with transaction.atomic():
        # because we're deleting all of the objects used by invalidate_cache() to determine how
        # to invalidate the cache prior to deleting the repository, we have to call it manually
        # rather than letting it be triggered as we delete the repository
        try:
            instance.invalidate_cache()
        except AttributeError:
            pass
        cascade_delete(
            serializer_class.Meta.model, instance._meta.model.objects.filter(pk=instance_id)
        )
