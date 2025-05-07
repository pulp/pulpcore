# Pulp Versioning

Pulp uses a version scheme `x.y.z`, which is based on [Semantic Versioning](http://semver.org/).
Briefly, `x.y.z` releases may only contain bugfixes (no features),
`x.y` releases may only contain backwards compatible changes (new features, bugfixes),
and `x` releases may break backwards compatibility.

!!! note

    In some rare cases, fixing a bug can only be done in a backwards incompatible way.
    This may happen in any release and even be backported.
    For obvious reasons we try to keep these cases to a minimum.

## Deprecation Policy for the Plugin API

The plugin API is provided by the pulpcore package.
However, it is not semantically versioned.
Backwards incompatible Plugin API changes are released in batches.
The version of such a breaking change release is announced well in advance.
Right before a breaking change release, the version of the next breaking change release is announced.
So far, the breaking change releases have occurred every 15 y-releases.

!!! note

    For example, at the time of this writing, the last breaking change release was `3.40` and the next will be `3.55.0`.
    So plugins should be safe to depend on `pulpcore>=3.42.0,<3.55` if depending on a feature introduced in `3.42.0`.
