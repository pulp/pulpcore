from gettext import gettext as _

from pulpcore.app.models import ContentArtifact
from pulpcore.app.files import validate_file_paths


def validate_publication_paths(publication):
    """
    Validate artifact relative paths for dupes or overlap (e.g. a/b and a/b/c).

    Raises:
        ValueError: If two artifact relative paths are dupes or overlap
    """
    paths = list(publication.published_artifact.values_list("relative_path", flat=True))

    if publication.pass_through:
        paths += ContentArtifact.objects.filter(
            content__pk__in=publication.repository_version.content
        ).values_list("relative_path", flat=True)

    try:
        validate_file_paths(paths)
    except ValueError as e:
        raise ValueError(_("Cannot create publication. {err}.").format(err=e))
