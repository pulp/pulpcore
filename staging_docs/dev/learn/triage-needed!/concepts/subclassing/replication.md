# Pulp Replication

The Pulp replication process allows a Pulp instance to discover distributions on an upstream Pulp
and create the necessary remotes, repositories, and distributions to serve the same content as the
upstream Pulp. To be 'replication' compatible, your plugin must define a `replicator` module at
`<plugin>/app/replica.py`. The module must contain a Replicator subclass for each distribution
type you want to be able to replicate. The module must also define `REPLICATION_ORDER` ordered
list for all such replicators.
