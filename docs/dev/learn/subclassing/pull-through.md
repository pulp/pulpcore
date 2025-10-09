# Pull-Through Caching

Pull-through caching enables plugins to use remotes on their distributions that will act as an
upstream fallback source when an user requests content from Pulp. The content will be streamed from
the remote and saved in Pulp to be served again in future requests. This feature requires plugins to
provide implementations for the methods below on the subclasses of their Remote and Content objects.

::: pulpcore.app.models.Remote.get_remote_artifact_url

::: pulpcore.app.models.Remote.get_remote_artifact_content_type

::: pulpcore.app.models.Content.init_from_artifact_and_relative_path

Finally, plugin writers need to expose the `remote` field on their distribution serializer to allow
users to add their remotes to their distributions. The `remote` field is already present on the base
distribution model, so no new migration is needed.

```python
class GemDistributionSerializer(DistributionSerializer):
    """A Serializer for GemDistribution."""

    ...

    remote = DetailRelatedField(
        required=False,
        help_text=_("Remote that can be used to fetch content when using pull-through caching."),
        view_name_pattern=r"remotes(-.*/.*)?-detail",
        queryset=Remote.objects.all(),
        allow_null=True,
    )

    class Meta:
        fields = DistributionSerializer.Meta.fields + ("publication", "remote")
        model = GemDistribution
```
