Added a new concept, `SharedAttributeManager`, to Pulp.

This feature allows attributes whose values are intended to
be the same, across multiple instances, to be managed from
one point. The feature can be accessed at `/pulp/api/v3/sams/`.
