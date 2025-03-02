# Checkpoint

!!! warning
    This feature is provided as a tech preview and could change in backwards incompatible
    ways in the future.

Pulp's checkpoint feature offers a robust way to manage and access historical versions of
repositories. By integrating checkpoints into your plugins, you enable users to recreate
environments from specific points in time, which is invaluable for identifying when changes or
regressions were introduced. This feature supports reproducible deployments, helps track changes in
package behavior, and facilitates a structured update workflow.

!!! warning
    The checkpoint feature is only supported for plugins using publications.

Plugin writers need to expose the `checkpoint` field on their distribution and publication
serializers to allow users to create checkpoint publications and create checkpoint distributions to
serve these publications. The `checkpoint` field is already present on the base distribution and
publication models, so no new migration is needed.

Example: enabling the checkpoint feature in the pulp_file plugin.
```python
class FileDistributionSerializer(DistributionSerializer):
    """
    Serializer for File Distributions.
    """
    publication = DetailRelatedField(
        required=False,
        help_text=_("Publication to be served"),
        view_name_pattern=r"publications(-.*/.*)?-detail",
        queryset=models.Publication.objects.exclude(complete=False),
        allow_null=True,
    )
    checkpoint = serializers.BooleanField(default=False)

    class Meta:
        fields = DistributionSerializer.Meta.fields + ("publication", "checkpoint")
        model = FileDistribution
```

```python
class FilePublicationSerializer(PublicationSerializer):
    """
    Serializer for File Publications.
    """
    distributions = DetailRelatedField(
        help_text=_("This publication is currently hosted as defined by these distributions."),
        source="distribution_set",
        view_name="filedistributions-detail",
        many=True,
        read_only=True,
    )
    manifest = serializers.CharField(
        help_text=_("Filename to use for manifest file containing metadata for all the files."),
        default="PULP_MANIFEST",
        required=False,
        allow_null=True,
    )
    checkpoint = serializers.BooleanField(default=False)

    class Meta:
        model = FilePublication
        fields = PublicationSerializer.Meta.fields + ("distributions", "manifest", "checkpoint")
```