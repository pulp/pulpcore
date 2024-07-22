from gettext import gettext as _

from django.conf import settings
from rest_framework.serializers import ValidationError

from pulpcore.app.models import Group, Repository


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


def has_domain_perms(request, view, action, permission):
    """
    Checks if the user has current domain-level permission.

    If DOMAIN_ENABLED, use the incoming request's domain for the permission check, else return
    False.
    """
    if settings.DOMAIN_ENABLED:
        return request.user.has_perm(permission, obj=request.pulp_domain)
    return False


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


def has_model_or_domain_perms(request, view, action, permission):
    """
    Checks if the current user has either model-level (global) or domain-level permissions.
    """
    return has_model_perms(request, view, action, permission) or has_domain_perms(
        request, view, action, permission
    )


def has_model_or_domain_or_obj_perms(request, view, action, permission):
    """
    Checks if the current user has the permission across all levels of Pulp.

    This checks all three levels of permissions in Pulp: model, domain, and object level. Returns
    True if the user has the permission on any of those levels, False otherwise.
    """
    return has_model_or_domain_perms(request, view, action, permission) or has_obj_perms(
        request, view, action, permission
    )


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
    return has_model_perms(request, view, action, permission) or has_obj_perms(
        request, view, action, permission
    )


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
            parameter at the object-level or if there is no remote. False otherwise.
    """
    kwargs = {}
    obj = view.get_object() if view.detail else None
    context = {"request": request}
    if obj:
        context["repository_pk"] = obj.pk
    if action == "partial_update":
        kwargs["partial"] = True
    serializer = view.serializer_class(instance=obj, data=request.data, context=context, **kwargs)
    serializer.is_valid(raise_exception=True)
    if remote := serializer.validated_data.get("remote"):
        return request.user.has_perm(permission, remote)
    return True


def has_remote_param_model_or_domain_or_obj_perms(request, view, action, permission):
    """
    Checks if the current user has the permission on the ``remote`` param.
    """
    return has_model_or_domain_perms(
        request, view, action, permission
    ) or has_remote_param_obj_perms(request, view, action, permission)


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
    return has_model_perms(request, view, action, permission) or has_remote_param_obj_perms(
        request, view, action, permission
    )


# 'Repository' attribute checks for RepositoryVersionViewSet


def has_repo_attr_obj_perms(request, view, action, permission):
    """
    Checks if the current user has object-level permission on a ``repository`` attribute.

    The object in this case is the one specified by the ``repository`` attribute of a resource
    which is being operated on. For example, when deleting a repository version, a ``repository``
    is its attribute.

    This is usable as a conditional check in an AccessPolicy. Here is an example checking for the
    "file.view_filerepository" permissions at the object-level.

    ::

        {
            ...
            "condition": "has_repo_attr_obj_perms:file.view_filerepository",
        }

    Since it is checking a ``repository`` object the permission argument should be one of the
    following:

    * "file.change_filerepository" - Permission to change the ``FileRepository``.
    * "file.view_filerepository" - Permission to view the ``FileRepository``.
    * "file.delete_filerepository" - Permission to delete the ``FileRepository``.
    * any custom permission a plugin has defined for their repository.

    Args:
        request (rest_framework.request.Request): The request being made.
        view (subclass rest_framework.viewsets.GenericViewSet): The view being checked for
            authorization.
        action (str): The action being performed, e.g. "destroy".
        permission (str): The name of the repository Permission to be checked. In the form
            `app_label.codename`, e.g. "file.delete_filerepository".

    Returns:
        True if the user has the Permission named by the ``permission`` argument on the
        ``repository`` attribute at the object-level. False otherwise.
    """
    plugin_repository = view.get_object().repository.cast()
    return request.user.has_perm(permission, plugin_repository)


def has_repo_attr_model_or_domain_or_obj_perms(request, view, action, permission):
    """
    Checks if the current user has the permission on the ``repository`` attribute.
    """
    return has_model_or_domain_perms(request, view, action, permission) or has_repo_attr_obj_perms(
        request, view, action, permission
    )


def has_repo_attr_model_or_obj_perms(request, view, action, permission):
    """
    Checks if the current user has model-level or object-level permissions on a ``repository``.

    The object in this case is the one specified by the ``repository`` attribute of a resource
    which is being operated on. For example, when deleting a repository version, a ``repository``
    is its attribute.

    This is usable as a conditional check in an AccessPolicy. Here is an example checking for the
    "file.view_filerepository" permissions at the object-level.

    ::

        {
            ...
            "condition": "has_repo_attr_model_or_obj_perms:file.view_filerepository",
        }

    Since it is checking a ``repository`` object the permission argument should be one of the
    following:

    * "file.change_filerepository" - Permission to change the ``FileRepository``.
    * "file.view_filerepository" - Permission to view the ``FileRepository``.
    * "file.delete_filerepository" - Permission to delete the ``FileRepository``.
    * any custom permission a plugin has defined for their repository.

    Args:
        request (rest_framework.request.Request): The request being made.
        view (subclass rest_framework.viewsets.GenericViewSet): The view being checked for
            authorization.
        action (str): The action being performed, e.g. "destroy".
        permission (str): The name of the repository Permission to be checked. In the form
            `app_label.codename`, e.g. "file.delete_filerepository".

    Returns:
        True if the user has the Permission on the ``repository`` attribute named by the
        ``permission`` at the model or object level. False otherwise.
    """
    return has_model_perms(request, view, action, permission) or has_repo_attr_obj_perms(
        request, view, action, permission
    )


def has_repository_obj_perms(request, view, action, permission):
    """
    Checks whether a user has the requested object permission on the repository in the URL.

    This check is meant to be used for relations nested beneath a repository endpoint, e.g. the
    list of repository versions belonging to that repository. It will fail for other endpoints.

    ::

        {
            ...
            "condition": "has_repository_obj_perms:file.filerepository_delete",
        },

    Args:
        request (rest_framework.request.Request): The request being made.
        view (subclass rest_framework.viewsets.GenericViewSet): The view being checked for
            authorization.
        action (str): The action being performed, e.g. "destroy".
        permission (str): The name of the Repository Permission to be checked. In the form
            `app_label.codename`, e.g. "file.filerepository_change".

    Returns:
        True if the user has the Permission on the ``Repository`` specified in the URL named by the
        ``permission`` at object level. False otherwise.
    """
    plugin_repository = Repository.objects.get(pk=view.kwargs["repository_pk"]).cast()
    return request.user.has_perm(permission, plugin_repository)


def has_repository_model_or_domain_or_obj_perms(request, view, action, permission):
    """
    Checks if the current user has the permission for the repository in the URL.
    """
    return has_model_or_domain_perms(request, view, action, permission) or has_repository_obj_perms(
        request, view, action, permission
    )


def has_repository_model_or_obj_perms(request, view, action, permission):
    """
    Checks whether a user has the requested model or object permission on the repository in the
    URL.

    This check is meant to be used for relations nested beneath a repository endpoint, e.g. the
    list of repository versions belonging to that repository. It will fail for other endpoints.

    ::

        {
            ...
            "condition": "has_repository_model_or_obj_perms:file.filerepository_delete",
        },

    Args:
        request (rest_framework.request.Request): The request being made.
        view (subclass rest_framework.viewsets.GenericViewSet): The view being checked for
            authorization.
        action (str): The action being performed, e.g. "destroy".
        permission (str): The name of the Repository Permission to be checked. In the form
            `app_label.codename`, e.g. "file.filerepository_change".

    Returns:
        True if the user has the Permission on the ``Repository`` specified in the URL named by the
        ``permission`` at model or object level. False otherwise.
    """
    return request.user.has_perm(permission) or has_repository_obj_perms(
        request, view, action, permission
    )


def has_repo_or_repo_ver_param_model_or_domain_or_obj_perms(request, view, action, permission):
    """
    Checks if the current user has permission on the ``repository`` or ``repository_version``.
    """
    if has_model_or_domain_perms(request, view, action, permission):
        return True
    kwargs = {}
    obj = view.get_object() if view.detail else None
    if action == "partial_update":
        kwargs["partial"] = True
    serializer = view.serializer_class(
        instance=obj, data=request.data, context={"request": request}, **kwargs
    )
    serializer.is_valid(raise_exception=True)
    if repository := serializer.validated_data.get("repository"):
        return request.user.has_perm(permission, repository.cast())
    elif repo_ver := serializer.validated_data.get("repository_version"):
        return request.user.has_perm(permission, repo_ver.repository.cast())
    return True


def has_repo_or_repo_ver_param_model_or_obj_perms(request, view, action, permission):
    """
    Checks if the current user has object-level permission on the ``repository`` object.

    The object in this case is the one specified by the ``repository`` or ``repository_version``
    parameter. For example when publishing the ``repository`` parameter is passed in as an argument.

    This is usable as a conditional check in an AccessPolicy. Here is an example checking for the
    "file.view_filerepository" permissions at the object-level.

    ::

        {
            ...
            "condition": "has_repo_or_repo_ver_param_model_or_obj_perms:file.view_filerepository",
        }

    Since it is checking a ``repository`` object the permission argument should be one of the
    following:

    * "file.change_filerepository" - Permission to change the ``FileRepository``.
    * "file.view_filerepository" - Permission to view the ``FileRepository``.
    * "file.delete_filerepository" - Permission to delete the ``FileRepository``.
    * "file.sync_filerepository" - Permission to sync the ``FileRepository``.

    Args:
        request (rest_framework.request.Request): The request being made.
        view (subclass rest_framework.viewsets.GenericViewSet): The view being checked for
            authorization.
        action (str): The action being performed, e.g. "destroy".
        permission (str): The name of the Permission to be checked. In the form
            `app_label.codename`, e.g. "core.delete_task".

    Returns:
        True if the user has the Permission named by the ``permission`` argument on the
            ``repository`` or ``repository_version`` parameter at the object-level or if there is
            no repository. False otherwise.
    """
    if has_model_perms(request, view, action, permission):
        return True
    kwargs = {}
    obj = view.get_object() if view.detail else None
    if action == "partial_update":
        kwargs["partial"] = True
    serializer = view.serializer_class(
        instance=obj, data=request.data, context={"request": request}, **kwargs
    )
    serializer.is_valid(raise_exception=True)
    if repository := serializer.validated_data.get("repository"):
        return request.user.has_perm(permission, repository.cast())
    elif repo_ver := serializer.validated_data.get("repository_version"):
        return request.user.has_perm(permission, repo_ver.repository.cast())
    return True


def has_required_repo_perms_on_upload(request, view, action, permission):
    """
    Checks if the current user has permission to upload content to the ``repository`` object.

    Since content queryset scoping prevents users from seeing orphaned content by default this
    also checks to make sure that any user that isn't an admin has also supplied the ``repository``
    parameter when performing a content upload.

    This is usable as a conditional check in an AccessPolicy for content uploads. Here is an
    example checking for the "file.modify_filerepository" permission.

    ::

        {
            ...
            "condition": "has_required_repo_perms_on_upload:file.modify_filerepository",
        }

    Args:
        request (rest_framework.request.Request): The request being made.
        view (subclass rest_framework.viewsets.GenericViewSet): The view being checked for
            authorization.
        action (str): The action being performed, e.g. "destroy".
        permission (str): The name of the Permission to be checked. In the form
            `app_label.codename`, e.g. "core.delete_task".

    Returns:
        True if the user has supplied the ``repository`` parameter and has the Permission on it
            named by the ``permission`` argument, or is an admin. False otherwise.
    """
    if request.user.is_superuser:
        return True
    obj = view.get_object() if view.detail else None
    serializer = view.serializer_class(
        instance=obj, data=request.data, context={"request": request}
    )
    serializer.is_valid(raise_exception=True)
    if repository := serializer.validated_data.get("repository"):
        if has_model_or_domain_perms(request, view, action, permission):
            return True
        return request.user.has_perm(permission, repository)
    if not request.user.is_superuser and not repository:
        raise ValidationError(_("Destination upload repository was not provided."))
    return False


def has_publication_param_model_or_domain_or_obj_perms(request, view, action, permission):
    """
    Checks if the current user has permission on the ``Publication`` param.
    """
    if has_model_or_domain_perms(request, view, action, permission):
        return True
    kwargs = {}
    obj = view.get_object() if view.detail else None
    if action == "partial_update":
        kwargs["partial"] = True
    serializer = view.serializer_class(
        instance=obj, data=request.data, context={"request": request}, **kwargs
    )
    serializer.is_valid(raise_exception=True)
    if publication := serializer.validated_data.get("publication"):
        return request.user.has_perm(permission, publication)
    return True


def has_publication_param_model_or_obj_perms(request, view, action, permission):
    """
    Checks if the current user has permission on the ``Publication`` object.

    The object in this case is the one specified by the ``publication`` parameter. For example when
    distributing the ``publication`` parameter is passed in as an argument.

    This is usable as a conditional check in an AccessPolicy. Here is an example checking for the
    "file.view_filepublication" permission.

    ::

        {
            ...
            "condition": "has_publication_param_model_or_obj_perms:file.view_filepublication",
        }

    Since it is checking a ``Publication`` object the permission argument should be one of the
    following:

    * "file.view_filepublication" - Permission to view the ``FilePublication``.
    * "file.delete_filepublication" - Permission to delete the ``FilePublication``.

    Args:
        request (rest_framework.request.Request): The request being made.
        view (subclass rest_framework.viewsets.GenericViewSet): The view being checked for
            authorization.
        action (str): The action being performed, e.g. "destroy".
        permission (str): The name of the Permission to be checked. In the form
            `app_label.codename`, e.g. "core.delete_task".

    Returns:
        True if the user has the Permission named by the ``permission`` argument on the
            ``publication`` parameter or if there is no publication. False otherwise.
    """
    if has_model_perms(request, view, action, permission):
        return True
    kwargs = {}
    obj = view.get_object() if view.detail else None
    if action == "partial_update":
        kwargs["partial"] = True
    serializer = view.serializer_class(
        instance=obj, data=request.data, context={"request": request}, **kwargs
    )
    serializer.is_valid(raise_exception=True)
    if publication := serializer.validated_data.get("publication"):
        return request.user.has_perm(permission, publication)
    return True


def has_upload_param_model_or_domain_or_obj_perms(request, view, action, permission):
    """
    Checks if the current user has permission on the ``Upload`` param.
    """
    if has_model_or_domain_perms(request, view, action, permission):
        return True
    kwargs = {}
    obj = view.get_object() if view.detail else None
    if action == "partial_update":
        kwargs["partial"] = True
    serializer = view.serializer_class(
        instance=obj, data=request.data, context={"request": request}, **kwargs
    )
    serializer.is_valid(raise_exception=True)
    if upload := serializer.validated_data.get("upload"):
        return request.user.has_perm(permission, upload)
    return True


def has_upload_param_model_or_obj_perms(request, view, action, permission):
    """
    Checks if the current user has permission on the ``Upload`` object.

    The object in this case is the one specified by the ``upload`` parameter, for example to a
    one-shot content creation call.

    This is usable as a conditional check in an AccessPolicy. Here is an example checking for the
    "core.change_upload" permissions.

    ::

        {
            ...
            "condition": "has_upload_param_model_or_obj_perms:core.change_upload",
        }

    Since it is checking a ``Upload`` object the permission argument should be one of the following:

    * "core.view_upload" - Permission to view the ``Upload``.
    * "core.change_upload" - Permission to change the ``Upload``.
    * "core.delete_upload" - Permission to delete the ``Upload``.

    Args:
        request (rest_framework.request.Request): The request being made.
        view (subclass rest_framework.viewsets.GenericViewSet): The view being checked for
            authorization.
        action (str): The action being performed, e.g. "destroy".
        permission (str): The name of the Permission to be checked. In the form
            `app_label.codename`, e.g. "core.delete_task".

    Returns:
        True if the user has the Permission named by the ``permission`` argument on the
            ``Upload`` parameter or if there is no upload. False otherwise.
    """
    if has_model_perms(request, view, action, permission):
        return True
    kwargs = {}
    obj = view.get_object() if view.detail else None
    if action == "partial_update":
        kwargs["partial"] = True
    serializer = view.serializer_class(
        instance=obj, data=request.data, context={"request": request}, **kwargs
    )
    serializer.is_valid(raise_exception=True)
    if upload := serializer.validated_data.get("upload"):
        return request.user.has_perm(permission, upload)
    return True


# `Group` permission checks


def has_group_obj_perms(request, view, action, permission):
    """
    Checks whether a user has the requested object permission on the Group in the URL.

    This check is meant to be used for relations nested beneath the group endpoint, e.g. the list
    of users to belong to that group. It will fail for other endpoints.

    ::

        {
            ...
            "condition": "has_group_obj_perms:core.group_delete",
        },

    Args:
        request (rest_framework.request.Request): The request being made.
        view (subclass rest_framework.viewsets.GenericViewSet): The view being checked for
            authorization.
        action (str): The action being performed, e.g. "destroy".
        permission (str): The name of the Group Permission to be checked. In the form
            `app_label.codename`, e.g. "core.group_change".

    Returns:
        True if the user has the Permission on the ``Group`` specified in the URL named by the
        ``permission`` at object level. False otherwise.
    """
    group_pk = request.resolver_match.kwargs["group_pk"]
    return request.user.has_perm(permission, Group.objects.get(pk=group_pk))


def has_group_model_or_obj_perms(request, view, action, permission):
    """
    Checks whether a user has the requested object or model permission on the Group in the URL.

    This check is meant to be used for relations nested beneath the group endpoint, e.g. the list
    of users to belong to that group. It will fail for other endpoints.

    ::

        {
            ...
            "condition": "has_group_model_or_obj_perms:core.group_delete",
        },

    Args:
        request (rest_framework.request.Request): The request being made.
        view (subclass rest_framework.viewsets.GenericViewSet): The view being checked for
            authorization.
        action (str): The action being performed, e.g. "destroy".
        permission (str): The name of the Group Permission to be checked. In the form
            `app_label.codename`, e.g. "core.group_change".

    Returns:
        True if the user has the Permission on the ``Group`` specified in the URL named by the
        ``permission`` at the model or object level. False otherwise.
    """
    return request.user.has_perm(permission) or has_group_obj_perms(
        request, view, action, permission
    )
