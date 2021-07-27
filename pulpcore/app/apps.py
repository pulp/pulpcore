from collections import defaultdict
from gettext import gettext as _
from importlib import import_module
import inspect
from itertools import groupby

from django import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.db.models.signals import post_migrate
from django.utils.module_loading import module_has_submodule

from pulpcore.exceptions.plugin import MissingPlugin

VIEWSETS_MODULE_NAME = "viewsets"
SERIALIZERS_MODULE_NAME = "serializers"
URLS_MODULE_NAME = "urls"
MODELRESOURCE_MODULE_NAME = "modelresource"
ROLES_MODULE_NAME = "roles"


def pulp_plugin_configs():
    """
    A generator of Pulp plugin AppConfigs

    This makes it easy to iterate over just the installed Pulp plugins when working
    with discovered plugin components.
    """
    for app_config in apps.apps.get_app_configs():
        if isinstance(app_config, PulpPluginAppConfig):
            yield app_config


def get_plugin_config(plugin_app_label):
    """
    A getter of specific pulp plugin config

    This makes it easy to retrieve a config for a specific Pulp plugin when looking for a
    registered model.

    Args:
        plugin_app_label (str): Django app label of the pulp plugin

    Returns:
        :class:`pulpcore.app.apps.PulpPluginAppConfig`: The app config of the Pulp plugin.

    Raises:
        MissingPlugin: When plugin with the requested app label is not installed.
    """
    for config in pulp_plugin_configs():
        if config.label == plugin_app_label:
            return config
    raise MissingPlugin(plugin_app_label)


class PulpPluginAppConfig(apps.AppConfig):
    """AppConfig class. Use this in plugins to identify your app as a Pulp plugin."""

    # Plugin behavior loading should happen in ready(), not in __init__().
    # ready() is called after all models are initialized, and at that point we should
    # be able to safely inspect the plugin modules to look for any components we need
    # to "register" with pulpcore. The viewset registration below is based on Django's
    # own model importing method.

    def __init__(self, app_name, app_module):
        super().__init__(app_name, app_module)

        try:
            self.version
        except AttributeError:
            msg = _(
                "The plugin `{}` is missing a version declaration. Starting with "
                "pulpcore==3.10, plugins are required to define their version on the "
                "PulpPluginAppConfig subclass."
            )
            raise ImproperlyConfigured(msg.format(self.label))

        # Module containing viewsets eg. <module 'pulp_plugin.app.viewsets'
        # from 'pulp_plugin/app/viewsets.py'>. Set by import_viewsets().
        # None if the application doesn't have a viewsets module, automatically set
        # when this app becomes ready.
        self.viewsets_module = None

        # Module containing urlpatterns
        self.urls_module = None

        # Module containing django-import-export ModelResources for a plugin's Models
        self.modelresource_module = None

        # List of classes from self.modelresource_module that can be exported
        self.exportable_classes = None

        # Mapping of model names to viewset lists (viewsets unrelated to models are excluded)
        self.named_viewsets = None

        # Mapping of serializer names to serializers
        self.named_serializers = None

        # List of Roles
        self.roles = []

    def ready(self):
        self.import_viewsets()
        self.import_serializers()
        self.import_urls()
        self.import_modelresources()
        self.import_roles()
        post_migrate.connect(_populate_access_policies, sender=self)
        post_migrate.connect(_handle_role_definition_changes, sender=self)

    def import_serializers(self):
        # circular import avoidance
        from pulpcore.app.serializers import ModelSerializer

        self.named_serializers = {}
        if module_has_submodule(self.module, SERIALIZERS_MODULE_NAME):
            # import the serializers module and track any discovered serializers
            serializers_module_name = "{name}.{module}".format(
                name=self.name, module=SERIALIZERS_MODULE_NAME
            )
            self.serializers_module = import_module(serializers_module_name)
            for objname in dir(self.serializers_module):
                obj = getattr(self.serializers_module, objname)
                try:
                    # Any subclass of ModelSerializer that isn't itself ModelSerializer
                    # gets registered in the named_serializers registry.
                    if obj is not ModelSerializer and issubclass(obj, ModelSerializer):
                        self.named_serializers[objname] = obj
                except TypeError:
                    # obj isn't a class, issubclass exploded but obj can be safely filtered out
                    continue

    def import_viewsets(self):
        # TODO do not include imported ViewSets
        # circular import avoidance
        from pulpcore.app.viewsets import NamedModelViewSet

        self.named_viewsets = defaultdict(list)
        if module_has_submodule(self.module, VIEWSETS_MODULE_NAME):
            # import the viewsets module and track any interesting viewsets
            viewsets_module_name = "{name}.{module}".format(
                name=self.name, module=VIEWSETS_MODULE_NAME
            )
            self.viewsets_module = import_module(viewsets_module_name)
            for objname in dir(self.viewsets_module):
                obj = getattr(self.viewsets_module, objname)
                try:
                    # Any subclass of NamedModelViewSet that isn't itself NamedModelViewSet
                    # gets registered in the named_viewsets registry.
                    if obj is not NamedModelViewSet and issubclass(obj, NamedModelViewSet):
                        model = obj.queryset.model
                        self.named_viewsets[model].append(obj)
                except TypeError:
                    # obj isn't a class, issubclass exploded but obj can be safely filtered out
                    continue

    def import_urls(self):
        """
        If a plugin defines a urls.py, include it.
        """
        if module_has_submodule(self.module, URLS_MODULE_NAME) and self.name != "pulpcore.app":
            urls_module_name = "{name}.{module}".format(name=self.name, module=URLS_MODULE_NAME)
            self.urls_module = import_module(urls_module_name)

    def import_modelresources(self):
        """
        If a plugin has a modelresource.py, import it

        (This exists when a plugin knows how to import-export itself)
        """
        if (
            module_has_submodule(self.module, MODELRESOURCE_MODULE_NAME)
            and self.name != "pulpcore.app"
        ):
            modelrsrc_module_name = "{name}.{module}".format(
                name=self.name, module=MODELRESOURCE_MODULE_NAME
            )
            self.modelresource_module = import_module(modelrsrc_module_name)
            self.exportable_classes = self.modelresource_module.IMPORT_ORDER

    def import_roles(self):
        """
        If a plugin defines a roles.py, include it.
        """
        from pulpcore.app.roles import Role

        def only_subclasses_of_Role(obj):
            return inspect.isclass(obj) and obj is not Role and issubclass(obj, Role)

        if module_has_submodule(self.module, ROLES_MODULE_NAME):
            roles_module_name = "{name}.{module}".format(name=self.name, module=ROLES_MODULE_NAME)
            roles_module = import_module(roles_module_name)
            for name, obj in inspect.getmembers(roles_module, only_subclasses_of_Role):
                self.roles.append(obj)


class PulpAppConfig(PulpPluginAppConfig):
    # The pulpcore app is itself a pulpcore plugin so that it can benefit from
    # the component discovery mechanisms provided by that superclass.

    # The app's importable name
    name = "pulpcore.app"

    # The app label to be used when creating tables, registering models, referencing this app
    # with manage.py, etc. This cannot contain a dot and must not conflict with the name of a
    # package containing a Django app.
    label = "core"

    # The version of this app
    version = "3.15.0.dev"

    def ready(self):
        super().ready()
        from . import checks  # noqa

        post_migrate.connect(_delete_anon_user, sender=self, dispatch_uid="delete_anon_identifier")


def _populate_access_policies(sender, **kwargs):
    from pulpcore.app.util import get_view_urlpattern

    apps = kwargs.get("apps")
    if apps is None:
        from django.apps import apps
    AccessPolicy = apps.get_model("core", "AccessPolicy")
    for viewset_batch in sender.named_viewsets.values():
        for viewset in viewset_batch:
            access_policy = getattr(viewset, "DEFAULT_ACCESS_POLICY", None)
            if access_policy is not None:
                viewset_name = get_view_urlpattern(viewset)
                db_access_policy, created = AccessPolicy.objects.get_or_create(
                    viewset_name=viewset_name, defaults=access_policy
                )
                if created:
                    print(f"Access policy for {viewset_name} created.")
                if not created and not db_access_policy.customized:
                    for key, value in access_policy.items():
                        setattr(db_access_policy, key, value)
                    db_access_policy.save()
                    print(f"Access policy for {viewset_name} updated.")


def _handle_role_definition_changes(sender, **kwargs):
    apps = kwargs.get("apps")
    if apps is None:
        from django.apps import apps
    RoleHistory = apps.get_model("core", "RoleHistory")
    User = get_user_model()
    from guardian.shortcuts import (
        assign_perm, get_objects_for_user, get_objects_for_group, remove_perm
    )
    from django.contrib.auth.models import Group
    from django.db.models import Count

    for role in sender.roles:
        name = f"{role.__module__}.{role.__name__}"
        try:
            role_history = RoleHistory.objects.get(role_obj_classpath=name)
        except RoleHistory.DoesNotExist:
            RoleHistory.objects.create(
                role_obj_classpath=name,
                permissions=role.permissions
            )
        else:
            added_role_permissions = set(role.permissions) - set(role_history.permissions)
            removed_role_permissions = set(role_history.permissions) - set(role.permissions)

            if added_role_permissions:
                existing_perms_qs = {}
                existing_perms = {}
                for key, perms_group in _get_perms_grouped_by_model(role_history.permissions):
                    list_of_perms = list(perms_group)
                    existing_perms[key] = list_of_perms
                    existing_perms_qs[key] = _get_as_permissions_qs(list_of_perms)
                for new_key, new_perms_group in _get_perms_grouped_by_model(added_role_permissions):
                    new_perms_qs = _get_as_permissions_qs(list(new_perms_group))
                    try:
                        old_perms_qs = existing_perms_qs[new_key]
                        old_perms_codenames = existing_perms[new_key]
                    except KeyError:
                        continue
                    else:
                        ## Add user-model-level perms
                        user_qs = User.objects.filter(user_permissions__in=list(old_perms_qs))
                        user_qs = user_qs.filter(is_superuser=False).annotate(num_perms=Count('id'))
                        user_qs = user_qs.filter(num_perms=len(old_perms_qs))
                        for user in user_qs:
                            for new_perm in new_perms_qs:
                                assign_perm(new_perm, user)

                        ## Add group-model-level perms
                        group_qs = Group.objects.filter(permissions__in=list(old_perms_qs))
                        group_qs = group_qs.annotate(num_perms=Count('id'))
                        group_qs = group_qs.filter(num_perms=len(old_perms_qs))
                        for group in group_qs:
                            for new_perm in new_perms_qs:
                                assign_perm(new_perm, group)

                        ## Add user-obj-level perms
                        # from guardian.models import UserObjectPermission
                        # qs = UserObjectPermission.objects.filter(permission__in=list(old_perms_qs))
                        for user in User.objects.all():
                            objs = get_objects_for_user(
                                user, old_perms_codenames, use_groups=False, with_superuser=False,
                                accept_global_perms=False
                            )
                            for obj in objs:
                                for new_perm in new_perms_qs:
                                    assign_perm(new_perm, user, obj)

                        ## Add group-obj-level perms
                        for group in Group.objects.all():
                            objs = get_objects_for_group(
                                group, old_perms_codenames, accept_global_perms=False
                            )
                            for obj in objs:
                                for new_perm in new_perms_qs:
                                    assign_perm(new_perm, group, obj)

            if removed_role_permissions:
                existing_perms_qs = {}
                existing_perms = {}
                for key, perms_group in _get_perms_grouped_by_model(role_history.permissions):
                    list_of_perms = list(perms_group)
                    existing_perms[key] = list_of_perms
                    existing_perms_qs[key] = _get_as_permissions_qs(list_of_perms)
                for removed_key, removed_perms_group in _get_perms_grouped_by_model(removed_role_permissions):
                    removed_perms_qs = _get_as_permissions_qs(list(removed_perms_group))
                    try:
                        old_perms_qs = existing_perms_qs[removed_key]
                        old_perms_codenames = existing_perms[removed_key]
                    except KeyError:
                        continue
                    else:
                        ## Remove user-model-level perms
                        user_qs = User.objects.filter(user_permissions__in=list(old_perms_qs))
                        user_qs = user_qs.filter(is_superuser=False).annotate(num_perms=Count('id'))
                        user_qs = user_qs.filter(num_perms=len(old_perms_qs))
                        for user in user_qs:
                            for removed_perm in removed_perms_qs:
                                remove_perm(removed_perm, user)

                        ## Remove group-model-level perms
                        group_qs = Group.objects.filter(permissions__in=list(old_perms_qs))
                        group_qs = group_qs.annotate(num_perms=Count('id'))
                        group_qs = group_qs.filter(num_perms=len(old_perms_qs))
                        for group in group_qs:
                            for removed_perm in removed_perms_qs:
                                remove_perm(removed_perm, group)

                        ## Remove user-obj-level perms
                        for user in User.objects.all():
                            objs = get_objects_for_user(
                                user, old_perms_codenames, use_groups=False, with_superuser=False,
                                accept_global_perms=False
                            )
                            for obj in objs:
                                for removed_perm in removed_perms_qs:
                                    remove_perm(removed_perm, user, obj)

                        ## Remove group-obj-level perms
                        for group in Group.objects.all():
                            objs = get_objects_for_group(
                                group, old_perms_codenames, accept_global_perms=False
                            )
                            for obj in objs:
                                for removed_perm in removed_perms_qs:
                                    remove_perm(removed_perm, group, obj)


def _get_as_permissions_qs(permissions):
    from django.contrib.auth.models import Permission
    codenames = [i.split('.')[1] for i in permissions]
    return Permission.objects.filter(codename__in=codenames)


def _get_perms_grouped_by_model(permission_set):
    from django.contrib.auth.models import Permission

    def key_func(perm_name):
        codename = perm_name.split('.')[1]
        return Permission.objects.get(codename=codename).content_type_id

    return groupby(permission_set, key_func)

def _delete_anon_user(sender, **kwargs):
    if settings.ANONYMOUS_USER_NAME is None:
        print(_("Deleting Guardians' AnonymousUser"))
        User = get_user_model()
        try:
            anon = User.objects.get(username="AnonymousUser")
        except User.DoesNotExist:
            pass
        else:
            anon.delete()
