Added new field `policy` to UpstreamPulp that decides how Replicate manages local objects within the domain.

Replicate will now copy the upstream's `pulp_labels` on downstream objects. Also, replicate will now
label the downstream objects created with the UpstreamPulp they came from.
