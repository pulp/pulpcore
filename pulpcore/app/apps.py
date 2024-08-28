import random

from collections import defaultdict
from gettext import gettext as _
from importlib import import_module

from django import apps
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import connection, transaction
from django.db.models.signals import post_migrate
from django.utils.module_loading import module_has_submodule

from pulpcore.exceptions.plugin import MissingPlugin


VIEWSETS_MODULE_NAME = "viewsets"
SERIALIZERS_MODULE_NAME = "serializers"
URLS_MODULE_NAME = "urls"
MODELRESOURCE_MODULE_NAME = "modelresource"
REPLICA_MODULE_NAME = "replica"

MODULE_PLUGIN_VERSIONS = {}


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
            msg = (
                "The plugin `{}` is missing a version declaration. Starting with pulpcore==3.10, "
                "plugins are required to define their version on the PulpPluginAppConfig subclass."
            )
            raise ImproperlyConfigured(msg.format(self.label))

        try:
            self.python_package_name
        except AttributeError:
            msg = (
                "The plugin `{}` is missing a `python_package_name` declaration. Starting with "
                "pulpcore==3.20, plugins are required to define the python package name providing "
                "the Pulp plugin on the PulpPluginAppConfig subclass as the `python_package_name` "
                "attribute."
            )
            raise ImproperlyConfigured(msg.format(self.label))
        if settings.DOMAIN_ENABLED:
            if not getattr(self, "domain_compatible", None):
                msg = (
                    "The plugin `{}-{}` is not domain compatible. Please uninstall/update the "
                    "plugin or turn off `DOMAIN_ENABLED` for Pulp to start."
                )
                raise ImproperlyConfigured(msg.format(self.python_package_name, self.version))
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

        # Module containing the replicator class for a plugin
        self.replicator_module = None
        # List of classes from the self.replicator_module
        self.replicator_classes = None

        # Mapping of model names to viewset lists (viewsets unrelated to models are excluded)
        self.named_viewsets = None
        # Mapping of serializer names to serializers
        self.named_serializers = None

    def ready(self):
        MODULE_PLUGIN_VERSIONS[self.__module__.split(".", maxsplit=1)[0]] = {
            self.label: self.version
        }
        self.import_viewsets()
        self.import_serializers()
        self.import_urls()
        self.import_modelresources()
        self.import_replicators()
        post_migrate.connect(
            _populate_access_policies,
            sender=self,
            dispatch_uid="populate_access_policies_identifier",
        )
        post_migrate.connect(_populate_roles, sender=self, dispatch_uid="populate_roles_identifier")

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
        from pulpcore.app.models import Repository, Content

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
                        if model is not Repository and issubclass(model, Repository):
                            Content._repository_types[Content].add(model)
                            for content in model.CONTENT_TYPES:
                                Content._repository_types[content].add(model)
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

    def import_replicators(self):
        """
        If a plugin has a replicator.py, import it.

        This exists when a plugin supports replication from an upstream Pulp.
        """
        if module_has_submodule(self.module, REPLICA_MODULE_NAME) and self.name != "pulpcore.app":
            replica_module_name = "{name}.{module}".format(
                name=self.name, module=REPLICA_MODULE_NAME
            )
            self.replicator_module = import_module(replica_module_name)
            self.replicator_classes = self.replicator_module.REPLICATION_ORDER


class PulpAppConfig(PulpPluginAppConfig):
    # The pulpcore app is itself a pulpcore plugin so that it can benefit from
    # the component discovery mechanisms provided by that superclass.

    # The app's importable name
    name = "pulpcore.app"

    default = True

    # The app label to be used when creating tables, registering models, referencing this app
    # with manage.py, etc. This cannot contain a dot and must not conflict with the name of a
    # package containing a Django app.
    label = "core"

    # The version of this app
    version = "3.49.18"

    # The python package name providing this app
    python_package_name = "pulpcore"

    domain_compatible = True

    def ready(self):
        super().ready()
        from . import checks  # noqa

        post_migrate.connect(
            _ensure_default_domain, sender=self, dispatch_uid="ensure_default_domain"
        )
        post_migrate.connect(
            _populate_system_id, sender=self, dispatch_uid="populate_system_id_identifier"
        )
        post_migrate.connect(
            _populate_artifact_serving_distribution,
            sender=self,
            dispatch_uid="populate_artifact_serving_distribution_identifier",
        )


def _populate_access_policies(sender, apps, verbosity, **kwargs):
    from pulpcore.app.util import get_view_urlpattern

    try:
        AccessPolicy = apps.get_model("core", "AccessPolicy")
    except LookupError:
        if verbosity >= 1:
            print(_("AccessPolicy model does not exist. Skipping initialization."))
        return

    for viewset_batch in sender.named_viewsets.values():
        for viewset in viewset_batch:
            access_policy = getattr(viewset, "DEFAULT_ACCESS_POLICY", None)
            if access_policy is not None:
                viewset_name = get_view_urlpattern(viewset)
                db_access_policy, created = AccessPolicy.objects.get_or_create(
                    viewset_name=viewset_name, defaults=access_policy
                )
                if created:
                    if verbosity >= 1:
                        print(
                            "Access policy for {viewset_name} created.".format(
                                viewset_name=viewset_name
                            )
                        )
                elif not db_access_policy.customized:
                    dirty = False
                    for key in ["statements", "creation_hooks", "queryset_scoping"]:
                        value = access_policy.get(key)
                        if getattr(db_access_policy, key, None) != value:
                            setattr(db_access_policy, key, value)
                            dirty = True
                    if dirty:
                        db_access_policy.save()
                        if verbosity >= 1:
                            print(
                                "Access policy for {viewset_name} updated.".format(
                                    viewset_name=viewset_name
                                )
                            )


def _populate_system_id(sender, apps, verbosity, **kwargs):
    SystemID = apps.get_model("core", "SystemID")
    if not SystemID.objects.exists():
        SystemID().save()


def _ensure_default_domain(sender, **kwargs):
    table_names = connection.introspection.table_names()
    if "core_domain" in table_names:
        from pulpcore.app.util import get_default_domain

        default = get_default_domain()  # Cache the default domain
        # Match the Pulp settings
        if (
            settings.HIDE_GUARDED_DISTRIBUTIONS != default.hide_guarded_distributions
            or settings.REDIRECT_TO_OBJECT_STORAGE != default.redirect_to_object_storage
            or settings.DEFAULT_FILE_STORAGE != default.storage_class
        ):
            default.hide_guarded_distributions = settings.HIDE_GUARDED_DISTRIBUTIONS
            default.redirect_to_object_storage = settings.REDIRECT_TO_OBJECT_STORAGE
            default.storage_class = settings.DEFAULT_FILE_STORAGE
            default.save(skip_hooks=True)


def _populate_roles(sender, apps, verbosity, **kwargs):
    role_prefix = f"{sender.label}."
    # collect all plugin defined roles
    desired_roles = {}
    for viewset_batch in sender.named_viewsets.values():
        for viewset in viewset_batch:
            locked_roles = getattr(viewset, "LOCKED_ROLES", None)
            if locked_roles is not None:
                desired_roles.update(locked_roles or {})
    adjust_roles(apps, role_prefix, desired_roles, verbosity)


def adjust_roles(apps, role_prefix, desired_roles, verbosity=1):
    """
    Adjust all roles with a given prefix.

    Args:
        apps (django.apps.registry.Apps): Django app registry
        role_prefix (str): Common prefix of roles to adjust
        desired_roles (dict): Dictionary of desired state of roles, where each entry is either a
            list of permissions, or a dict with "description" and "permissions" as keys.
    """
    assert all((key.startswith(role_prefix) for key in desired_roles))
    try:
        Role = apps.get_model("core", "Role")
        Permission = apps.get_model("auth", "Permission")
    except LookupError:
        # The signal might have been triggered on an old migration
        if verbosity >= 1:
            print(_("Role model does not exist. Skipping initialization."))
        return

    def _get_permission(perm):
        app_label, codename = perm.split(".", maxsplit=2)
        return Permission.objects.get(content_type__app_label=app_label, codename=codename)

    # Remove obsolete roles
    Role.objects.filter(name__startswith=role_prefix, locked=True).exclude(
        name__in=desired_roles.keys()
    ).delete()
    # Create / update desired roles
    for name, desired_role in desired_roles.items():
        if isinstance(desired_role, dict):
            description = desired_role.get("description")
            permissions = desired_role["permissions"]
        elif isinstance(desired_role, list):
            description = None
            permissions = desired_role
        else:
            raise RuntimeError(
                _("Locked role definition for {name} is incompatible.").format(name=name)
            )
        permissions = [_get_permission(perm) for perm in permissions]
        role, created = Role.objects.get_or_create(
            name=name, locked=True, defaults={"name": name, "locked": True}
        )
        role.description = description
        role.save()
        role.permissions.set(permissions)


def _populate_artifact_serving_distribution(sender, apps, verbosity, **kwargs):
    if (
        settings.DEFAULT_FILE_STORAGE == "pulpcore.app.models.storage.FileSystem"
        or not settings.REDIRECT_TO_OBJECT_STORAGE
    ):
        try:
            ArtifactDistribution = apps.get_model("core", "ArtifactDistribution")
            ContentRedirectContentGuard = apps.get_model("core", "ContentRedirectContentGuard")
        except LookupError:
            if verbosity >= 1:
                print(_("ArtifactDistribution model does not exist. Skipping initialization."))
            return
        try:
            ArtifactDistribution.objects.get()
        except ArtifactDistribution.DoesNotExist:
            name = f"{random.getrandbits(256):x}"
            with transaction.atomic():
                content_guard, _created = ContentRedirectContentGuard.objects.get_or_create(
                    name=name,
                    pulp_type="core.content_redirect",
                )
                _dist, _created = ArtifactDistribution.objects.get_or_create(
                    name=name,
                    pulp_type="core.artifact",
                    defaults={"base_path": name, "content_guard": content_guard},
                )
