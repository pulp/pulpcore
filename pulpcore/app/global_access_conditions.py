from pulpcore.app.serializers import RepositorySyncURLSerializer


# Model checks


def has_model_perms(request, view, action, permission):
    """
    Checks if the current user has a model-level permission.

    This is usable as a conditional check in an AccessPolicy. Here is an example checking for
    "file.add_fileremote" permission at the model-level.

    ::

        {
            ...
            "condition": "has_model_perms:file.add_fileremote",
        }

    Args:
        request (rest_framework.request.Request): The request being made.
        view (subclass rest_framework.viewsets.GenericViewSet): The view being checked for
            authorization.
        action (str): The action being performed, e.g. "destroy".
        permission (str): The name of the Permission to be checked. In the form
            `app_label.codename`, e.g. "core.delete_task".

    Returns:
        True if the user has the Permission named by the ``permission`` argument at the model-level.
            False otherwise.
    """
    return request.user.has_perm(permission)


def has_obj_perms(request, view, action, permission):
    """
    Checks if the current user has object-level permission on the specific object.

    The object in this case is the one the action is operating on, e.g. the URL
    ``/pulp/api/v3/tasks/15939b47-6b6d-4613-a441-939ca4ba6e63/`` is operating on the Task object
    with ``pk=15939b47-6b6d-4613-a441-939ca4ba6e63``.

    This is usable as a conditional check in an AccessPolicy. Here is an example checking for the
    "file.view_fileremote" permissions at the object-level.

    ::

        {
            ...
            "condition": "has_obj_perms:file.view_fileremote",
        }

    Args:
        request (rest_framework.request.Request): The request being made.
        view (subclass rest_framework.viewsets.GenericViewSet): The view being checked for
            authorization.
        action (str): The action being performed, e.g. "destroy".
        permission (str): The name of the Permission to be checked. In the form
            `app_label.codename`, e.g. "core.delete_task".

    Returns:
        True if the user has the Permission named by the ``permission`` argument on the object being
            operated on at the object-level. False otherwise.
    """
    obj = view.get_object()
    return request.user.has_perm(permission, obj)


def has_model_or_obj_perms(request, view, action, permission):
    """
    Checks if the current user has either model-level or object-level permissions.

    The object in this case is the one the action is operating on, e.g. the URL
    ``/pulp/api/v3/tasks/15939b47-6b6d-4613-a441-939ca4ba6e63/`` is operating on the Task object
    with ``pk=15939b47-6b6d-4613-a441-939ca4ba6e63``.

    This is usable as a conditional check in an AccessPolicy. Here is an example checking for
    "file.view_fileremote" permission at either the model-level or object-level.

    ::

        {
            ...
            "condition": "has_model_or_obj_perms:file.view_fileremote",
        }

    Args:
        request (rest_framework.request.Request): The request being made.
        view (subclass rest_framework.viewsets.GenericViewSet): The view being checked for
            authorization.
        action (str): The action being performed, e.g. "destroy".
        permission (str): The name of the Permission to be checked. In the form
            `app_label.codename`, e.g. "core.delete_task".

    Returns:
        True if the user has the Permission named by the ``permission`` argument at the model-level
            or on the object being operated on at the object-level. False otherwise.
    """
    if has_model_perms(request, view, action, permission):
        return True
    if has_obj_perms(request, view, action, permission):
        return True
    return False


# 'Remote' parameter checks


def has_remote_param_obj_perms(request, view, action, permission):
    """
    Checks if the current user has object-level permission on the ``remote`` object.

    The object in this case is the one specified by the ``remote`` parameter. For example when
    syncing the ``remote`` parameter is passed in as an argument.

    This is usable as a conditional check in an AccessPolicy. Here is an example checking for the
    "file.view_fileremote" permissions at the object-level.

    ::

        {
            ...
            "condition": "has_remote_param_obj_perms:file.view_fileremote",
        }

    Since it is checking a ``remote`` object the permission argument should be one of the following:

    * "file.change_fileremote" - Permission to change the ``FileRemote``.
    * "file.view_fileremote" - Permission to view the ``FileRemote``.
    * "file.delete_fileremote" - Permission to delete the ``FileRemote``.

    Args:
        request (rest_framework.request.Request): The request being made.
        view (subclass rest_framework.viewsets.GenericViewSet): The view being checked for
            authorization.
        action (str): The action being performed, e.g. "destroy".
        permission (str): The name of the Permission to be checked. In the form
            `app_label.codename`, e.g. "core.delete_task".

    Returns:
        True if the user has the Permission named by the ``permission`` argument on the ``remote``
            parameter at the object-level. False otherwise.
    """
    serializer = RepositorySyncURLSerializer(data=request.data, context={"request": request})
    serializer.is_valid(raise_exception=True)
    remote = serializer.validated_data.get("remote")
    return request.user.has_perm(permission, remote)


def has_remote_param_model_or_obj_perms(request, view, action, permission):
    """
    Checks if the current user has either model-level or object-level permissions on the ``remote``.

    The object in this case is the one specified by the ``remote`` parameter. For example when
    syncing the ``remote`` parameter is passed in as an argument.

    This is usable as a conditional check in an AccessPolicy. Here is an example checking for
    "file.view_fileremote" permission at either the model-level or object-level.

    ::

        {
            ...
            "condition": "has_remote_param_model_or_obj_perms:file.view_fileremote",
        }

    Since it is checking a ``remote`` object the permission argument should be one of the following:

    * "file.change_fileremote" - Permission to change the ``FileRemote``.
    * "file.view_fileremote" - Permission to view the ``FileRemote``.
    * "file.delete_fileremote" - Permission to delete the ``FileRemote``.

    Args:
        request (rest_framework.request.Request): The request being made.
        view (subclass rest_framework.viewsets.GenericViewSet): The view being checked for
            authorization.
        action (str): The action being performed, e.g. "destroy".
        permission (str): The name of the Permission to be checked. In the form
            `app_label.codename`, e.g. "core.delete_task".

    Returns:
        True if the user has the Permission named by the ``permission`` at the model-level or on the
            argument on the ``remote`` parameter at the object-level. False otherwise.
    """
    if has_model_perms(request, view, action, permission):
        return True
    if has_remote_param_obj_perms(request, view, action, permission):
        return True
    return False
