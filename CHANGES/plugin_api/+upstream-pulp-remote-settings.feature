Renamed the `Replicator` constructor parameter and instance attribute from `tls_settings` to
`remote_settings` to reflect the expanded set of remote configuration fields propagated during
replication. The old `tls_settings` attribute is still available as a deprecated alias.
