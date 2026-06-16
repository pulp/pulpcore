Add `/v4/` API to Pulp.

This adds a `/v4/` API path to Pulp, in parallel to the existing `/v3/` path. The two
are currently (nearly) identical APIs - see the `/pulp/api/v4/status/` ouput for the
only (current) end-user-visible impact.

This change is primarily setting the stage to allow for future API changes and growth.
It is in TECH PREVIEW, and is likely to have significant changes happening to it as we
continue integrating into the rest of the Pulp architecture.
