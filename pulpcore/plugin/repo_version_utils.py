from gettext import gettext as _
import logging

from django.db.models import Q

from pulpcore.app.files import validate_file_paths
from pulpcore.app.models import Content, ContentArtifact
from pulpcore.app.util import batch_qs


_logger = logging.getLogger(__name__)

__all__ = ["remove_duplicates"]


def remove_duplicates(repository_version):
    """
    Inspect content additions in the `RepositoryVersion` and remove existing repository duplicates.

    This function will inspect the content being added to a repo version and remove any existing
    content which would collide with the content being added to the repository version. It does not
    inspect the content being added for duplicates.

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
    added_content = repository_version.added(base_version=repository_version.base_version)
    if repository_version.base_version:
        existing_content = repository_version.base_version.content
    else:
        try:
            existing_content = repository_version.previous().content
        except repository_version.DoesNotExist:
            existing_content = Content.objects.none()
    repository = repository_version.repository.cast()
    content_types = {type_obj.get_pulp_type(): type_obj for type_obj in repository.CONTENT_TYPES}

    for pulp_type, type_obj in content_types.items():
        repo_key_fields = type_obj.repo_key_fields
        new_content_qs = type_obj.objects.filter(
            pk__in=added_content.filter(pulp_type=pulp_type)
        ).values(*repo_key_fields)

        if type_obj.repo_key_fields == ():
            continue

        if new_content_qs.count() and existing_content.count():
            _logger.debug(_("Removing duplicates for type: {}".format(type_obj.get_pulp_type())))

            for batch in batch_qs(new_content_qs):
                find_dup_qs = Q()

                for content_dict in batch:
                    item_query = Q(**content_dict)
                    find_dup_qs |= item_query

                duplicates_qs = (
                    type_obj.objects.filter(pk__in=existing_content).filter(find_dup_qs).only("pk")
                )
                repository_version.remove_content(duplicates_qs)


def validate_duplicate_content(version):
    """
    Validate that a repository version doesn't contain duplicate content.

    Uses repo_key_fields to determine if content is duplicated.

    Raises:
        ValueError: If repo version has duplicate content.
    """
    error_messages = []

    for type_obj in version.repository.CONTENT_TYPES:
        if type_obj.repo_key_fields == ():
            continue

        pulp_type = type_obj.get_pulp_type()
        repo_key_fields = type_obj.repo_key_fields
        new_content_total = type_obj.objects.filter(
            pk__in=version.content.filter(pulp_type=pulp_type)
        ).count()
        unique_new_content_total = (
            type_obj.objects.filter(pk__in=version.content.filter(pulp_type=pulp_type))
            .distinct(*repo_key_fields)
            .count()
        )

        if unique_new_content_total < new_content_total:
            error_messages.append(
                _(
                    "More than one {pulp_type} content with the duplicate values for {fields}."
                ).format(pulp_type=pulp_type, fields=", ".join(repo_key_fields))
            )
    if error_messages:
        raise ValueError(
            _("Cannot create repository version. {msg}").format(msg=", ".join(error_messages))
        )


def validate_version_paths(version):
    """
    Validate artifact relative paths for dupes or overlap (e.g. a/b and a/b/c).

    Raises:
        ValueError: If two artifact relative paths overlap
    """
    paths = ContentArtifact.objects.filter(content__pk__in=version.content).values_list(
        "relative_path", flat=True
    )
    try:
        validate_file_paths(paths)
    except ValueError as e:
        raise ValueError(_("Repository version errors : {err}").format(err=e))


def validate_repo_version(version):
    """
    Validate a repo version.

    Checks for duplicate content, duplicate relative paths, etc.

    Raises:
        ValueError: If repo version is not valid.
    """
    validate_duplicate_content(version)
    validate_version_paths(version)
