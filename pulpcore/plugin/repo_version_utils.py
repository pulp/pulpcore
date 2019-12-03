from gettext import gettext as _
import logging

from django.db.models import Q

from pulpcore.app.models import Content, ContentArtifact
from pulpcore.app.util import batch_qs
from pulpcore.app.files import validate_file_paths


_logger = logging.getLogger(__name__)

__all__ = ["remove_duplicates"]


def remove_duplicates(repository_version):
    """
    Inspect content additions in the `RepositoryVersion` and replace repository duplicates.

    Some content can have two instances A and B which are unique, but cannot both exist together in
    one repository. For example, pulp_file's content has `relative_path` for that file within the
    repository.

    Any content newly added to the :class:`~pulpcore.plugin.models.RepositoryVersion` is checked
    against existing content in the :class:`~pulpcore.plugin.models.RepositoryVersion` with newer
    "repository duplicates" replace existing "repository duplicates". Each Content model can define
    a `repo_key_fields` attribute with the field names to be compared. If all `repo_key_fields`
    contain the same value for two content units, they are considered "repository duplicates".

    Args:
        repository_version: The :class:`~pulpcore.plugin.models.RepositoryVersion` to be checked
            and possibly modified.
    """
    repository_type = repository_version.repository.pulp_type.split(".")[-1]
    CONTENT_TYPES = [
        f.name for f in Content._meta.get_fields() if f.name.startswith(repository_type)
    ]

    for content_type in CONTENT_TYPES:
        first_content = getattr(Content, content_type, None).get_queryset().first()
        if not first_content:
            continue

        repo_key_fields = first_content.repo_key_fields
        if repo_key_fields == ():
            continue

        model = first_content._meta.model
        if "pk" not in repo_key_fields:
            repo_key_fields = repo_key_fields + ("pk",)

        added_batch = batch_qs(model.objects.filter(
            version_memberships__version_added=repository_version
        ).values(*repo_key_fields))

        queryset = None
        for added in added_batch:
            query_for_repo_duplicates_by_type = Q()
            for item in added:
                pk = str(item.pop("pk"))
                item_query = Q(**item) & ~Q(pk=pk)
                query_for_repo_duplicates_by_type |= item_query

            qs = model.objects.filter(query_for_repo_duplicates_by_type)
            if not queryset:
                queryset = qs
            else:
                queryset = queryset | qs

        _logger.debug(_("Removing duplicates for type: {}".format(model)))
        repository_version.remove_content(queryset)


def validate_version_paths(version):
    """
    Validate artifact relative paths for dupes or overlap (e.g. a/b and a/b/c).

    Raises:
        ValueError: If two artifact relative paths overlap
    """
    paths = ContentArtifact.objects. \
        filter(content__pk__in=version.content). \
        values_list("relative_path", flat=True)

    try:
        validate_file_paths(paths)
    except ValueError as e:
        raise ValueError(_("Cannot create repository version. {err}.").format(err=e))
