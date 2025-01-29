Added support to create and distribute checkpoint publications in Pulp.
Plugins can choose to enable this feature by exposing the checkpoint field in their inherited PublicationSerializer and DistributionSerializer.
Checkpoint publications and distributions can be created by passing checkpoint=True when creating them. 