# Adding Domain Compatibility to a Plugin

In order to enable Domains, all plugins must be Domain compatible or Pulp will refuse to start.
Since Domains is an optional feature,
becoming Domains compatible requires special handling for when the feature is on or off.

Follow the guide below to learn how to make your plugin Domain compatible.

## Add Domain Relation to Plugin Models

Objects will need to be updated to always have a relation to a `pulp_domain`,
which points to a default domain when the feature is disabled.
Most models that inherit from `pulpcore` models will already have a `pulp_domain` foreign key relation,
so this step mainly involves updating your plugin's custom models.
The one exception is models inheriting from `Content`.
These models need the `_pulp_domain` relation to be added onto the model and have their `unique_together` updated.
See the code below for an example:

```python
from pulpcore.plugin.util import get_domain_pk

class FileContent(Content):
    ...
    _pulp_domain = models.ForeignKey("core.Domain", default=get_domain_pk, on_delete=models.PROTECT)

    class Meta:
        unique_together = ("relative_path", "digest", "_pulp_domain")
```

!!! note

    Child content models need a separate domain relation,
    since Postgres does not allow `unique_together` on fields from the parent table.
    The base `Content` model has a `pulp_domain` relation already,
    so the child content model must use an underscore to prevent a name collision.

## Ensure any Custom Action Serializer Prevents Cross-Domain Parameters

Domains are strictly isolated from each other and thus two objects from different domains can not be used within the same task/operation.
The `pulpcore.app.serializers.ValidateFieldsMixin` contains a method for this check: `check_cross_domains`.
This is called during the `validate` method if this mixin is included in your serializer.
Custom serializers that take in multiple resources need to perform this check to ensure Domain validity.

## Update each Task that uses Objects to include the Domain field

Task code that uses objects needs to be updated to account for Domains.
Each task can access the current domain either through the current `Task`'s `pulp_domain` relation or through using `pulpcore.plugin.util.get_domain`.
These should be used to ensure you are only using objects within the correct `domain` of the task.
The [sync pipeline] has been updated to use the task's `domain` when querying and saving `Artifact` and `Content` units,
so simple sync-pipelines will probably need no update.
Similarly, when [creating a publication] with the context-manager,
the `pulp_domain` field is already properly handled on the `Publication`, `PublishedArtifacts` and `PublishedMetadata`.

```python
from pulpcore.plugin.models import Task
from pulpcore.plugin.util import get_domain
from .models import CustomModel

def custom_task(custom_property):
    # How to get the current domain for this task
    domain = Task.current().pulp_domain
    # Or with get_domain
    domain = get_domain()
    # Use only objects within the Task's domain
    objects = CustomModel.objects.filter(pulp_domain=domain)
```

## Add the Appropriate has_domain_perms Checks to the ViewSets' AccessPolicies

If your plugin uses [RBAC AccessPolicies],
then the current access condition checks need to be updated to use their Domain compatible variants.
These checks ensure that Domain-level permissions work properly in your ViewSets.
See the `permission_checking_machinery` documentation for all available checks.

## Update any extra URL Routes to include {pulp_domain}

Enabling Domains modifies the URL paths Pulp generates and custom routes added in `urls.py` need to add `{pulp_domain}` when `DOMAIN_ENABLED` is set.
Pulp has a custom Domain middleware that will remove the `pulp_domain` from the ViewSet's handler method args and attach it to the request object to prevent breaking current ViewSets.

## Add `domain_compatible = True` to `PluginAppConfig`

This attribute is what informs Pulp that your plugin is Domain compatible on startup.
Without this, Pulp will fail to start when enabling Domains.

## Add Tests

Adding custom tests for the most important actions is a good way to ensure your compatibility stays well maintained.
In your `template_config.yml`, change one-two runners to have `DOMAIN_ENABLED` set.
Use this setting in your custom Domains tests to check if they should be skipped.
When Domains are enabled the Python client bindings will require a `pulp_domain` name parameter on `list` and `create` actions.
This param has a default value of 'default' to prevent the need to rewrite existing tests.

```yaml
pulp_settings:
  orphan_protection_time: 0
pulp_settings_azure:
  domain_enabled: true
pulp_settings_s3:
  domain_enabled: true
pulp_settings_stream: null
```

## Add Documentation

Add Domain documentation to your workflows to show off your new features!

[creating a publication]: site:/pulpcore/docs/dev/learn/tasks/publish/
[rbac accesspolicies]: site:/pulpcore/docs/dev/learn/rbac/access_policy/
[sync pipeline]: site:/pulpcore/docs/dev/learn/sync_pipeline/sync_pipeline/
