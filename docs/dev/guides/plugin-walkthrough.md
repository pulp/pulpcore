# Plugin Walkthrough

This guide assumes that you are familiar with [general pulp concepts](site:pulpcore/docs/dev/learn/plugin-concepts/) as well as the `planning-guide`.
It will be helpful to skim the `plugin-concepts` pages, and refer back to them as you go
through the process.

## Bootstrap your plugin

Start your new plugin by using the [Plugin Template](https://github.com/pulp/plugin_template).
Follow the documentation in the README to get a working stub plugin.



## Define your plugin Content type

To define a new content type(s), e.g. `ExampleContent`:

- `pulpcore.plugin.models.Content` should be subclassed and extended with additional
  attributes to the plugin needs,
- define `TYPE` class attribute which is used for filtering purposes,
- uniqueness should be specified in `Meta` class of newly defined `ExampleContent` model,
- `unique_together` should be specified for the `Meta` class of `ExampleContent` model,
- create a serializer for your new Content type as a subclass of
  `pulpcore.plugin.serializers.NoArtifactContentSerializer`,
  `pulpcore.plugin.serializers.SingleArtifactContentSerializer`, or
  `pulpcore.plugin.serializers.MultipleArtifactContentSerializer`
- create a viewset for your new Content type. It can be as a subclass of
  `pulpcore.plugin.viewsets.ContentViewSet`, and you can define your `create()` method based
  on the serializer you chose. If you need a read-only viewset, subclass
  `pulpcore.plugin.viewsets.ReadOnlyContentViewSet` instead. It's also convenient to subclass
  `pulpcore.plugin.viewsets.SingleArtifactContentUploadViewSet` if you need an upload support.

`pulpcore.plugin.models.Content` model should not be used directly anywhere in plugin code.
Only plugin-defined Content classes are expected to be used.

Check `pulp_file` implementation of [the FileContent](https://github.com/pulp/pulpcore/blob/master/pulp_file/app/models.py) and its
[serializer](https://github.com/pulp/pulpcore/blob/master/pulp_file/app/serializers.py)
and [viewset](https://github.com/pulp/pulpcore/blob/master/pulp_file/app/viewsets.py).
For a general reference for serializers and viewsets, check [DRF documentation](http://www.django-rest-framework.org/api-guide/viewsets/).

Add any fields that correspond to the metadata of your content, which could be the project name,
the author name, or any other type of metadata.



## Define your plugin Remote

To define a new remote, e.g. `ExampleRemote`:

- `pulpcore.plugin.models.Remote` should be subclassed and extended with additional
  attributes to the plugin needs,
- define `TYPE` class attribute which is used for filtering purposes,
- create a serializer for your new remote as a subclass of
  `pulpcore.plugin.serializers.RemoteSerializer`,
- create a viewset for your new remote as a subclass of
  `pulpcore.plugin.viewsets.RemoteViewSet`.

`pulpcore.plugin.models.Remote` model should not be used directly anywhere in plugin code.
Only plugin-defined Remote classes are expected to be used.

There are several important aspects relevant to remote implementation which are briefly mentioned
in the `object-relationships` section:

- due to deduplication of `pulpcore.plugin.models.Content` and
  `pulpcore.plugin.models.Artifact` data, they may already exist and the remote needs to
  fetch and use them when they do.
- `pulpcore.plugin.models.ContentArtifact` associates
  `pulpcore.plugin.models.Content` and `pulpcore.plugin.models.Artifact`. If
  `pulpcore.plugin.models.Artifact` is not downloaded yet,
  `pulpcore.plugin.models.ContentArtifact` contains `NULL` value for
  `pulpcore.plugin.models.ContentArtifact.artifact`. It should be updated whenever
  corresponding `pulpcore.plugin.models.Artifact` is downloaded

!!! note

    Some of these steps may need to behave differently for other download policies.


The remote implementation suggestion above allows plugin writer to have an understanding and
control at a low level.

## Define your Tasks

See `writing-tasks`. Almost all plugins must implement a `sync` task, most implement a
`publish` task as well.

## Plugin Completeness Checklist

- Plugin django app is defined using PulpAppConfig as a parent
- Plugin entry point is defined
- `pulpcore` is specified as a requirement
- Necessary models/serializers/viewsets are defined and discoverable.
  At a minimum:
    - models for plugin content type, remote, publisher
    - serializers for plugin content type, remote, publisher
    - viewset for plugin content type, remote, publisher
- Errors are handled according to Pulp conventions
- Docs for plugin are available (any location and format preferred and provided by plugin writer)
