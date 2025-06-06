from django.db import transaction

from pulpcore.app.apps import get_plugin_config
from pulpcore.app.models import CreatedResource
from pulpcore.app.loggers import deprecation_logger
from pulpcore.plugin.models import MasterModel

from asgiref.sync import sync_to_async


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
    deprecation_logger.warning(
        "`pulpcore.app.tasks.base.general_update` is deprecated and will be removed in Pulp 4. "
        "Use `pulpcore.app.tasks.base.ageneral_update` instead."
    )
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
    deprecation_logger.warning(
        "`pulpcore.app.tasks.base.general_delete` is deprecated and will be removed in Pulp 4. "
        "Use `pulpcore.app.tasks.base.ageneral_delete` instead."
    )
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


async def ageneral_update(instance_id, app_label, serializer_name, *args, **kwargs):
    """
    Async version of [pulpcore.app.tasks.base.general_update][].
    """
    data = kwargs.pop("data", None)
    partial = kwargs.pop("partial", False)
    serializer_class = get_plugin_config(app_label).named_serializers[serializer_name]
    instance = await serializer_class.Meta.model.objects.aget(pk=instance_id)
    if isinstance(instance, MasterModel):
        instance = await instance.acast()
    serializer = serializer_class(instance, data=data, partial=partial)
    await sync_to_async(serializer.is_valid)(raise_exception=True)
    await sync_to_async(serializer.save)()


async def ageneral_delete(instance_id, app_label, serializer_name):
    """
    Async version of [pulpcore.app.tasks.base.general_delete][].
    """
    serializer_class = get_plugin_config(app_label).named_serializers[serializer_name]
    instance = await serializer_class.Meta.model.objects.aget(pk=instance_id)
    if isinstance(instance, MasterModel):
        instance = await instance.acast()
    await instance.adelete()
