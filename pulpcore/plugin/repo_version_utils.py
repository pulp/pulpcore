from gettext import gettext as _
import logging

from django.db.models import Q

from pulpcore.app.files import validate_file_paths
from pulpcore.app.models import Content, ContentArtifact
from pulpcore.app.util import batch_qs
from pulpcore.exceptions import DuplicateContentInRepositoryError
from collections import defaultdict
from django_guid import get_guid
from typing import NamedTuple


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

    Any content newly added to the [pulpcore.plugin.models.RepositoryVersion][] is checked
    against existing content in the [pulpcore.plugin.models.RepositoryVersion][] with newer
    "repository duplicates" replace existing "repository duplicates". Each Content model can define
    a `repo_key_fields` attribute with the field names to be compared. If all `repo_key_fields`
    contain the same value for two content units, they are considered "repository duplicates".

    Args:
        repository_version: The [pulpcore.plugin.models.RepositoryVersion][] to be checked
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
        RepositoryVersionCreateError: If repo version has duplicate content.
    """
    correlation_id = get_guid()
    dup_found = False
    for type_obj in version.repository.CONTENT_TYPES:
        if type_obj.repo_key_fields == ():
            continue
        dup_count = 0
        pulp_type = type_obj.get_pulp_type()
        unique_keys = type_obj.repo_key_fields
        content_qs = type_obj.objects.filter(pk__in=version.content.filter(pulp_type=pulp_type))
        dup_count += count_duplicates(content_qs, unique_keys)
        if dup_count > 0:
            # At this point the task already failed, so we'll pay extra queries
            # to collect duplicates and provide more useful logs
            dup_found = True
            for duplicate in collect_duplicates(content_qs, unique_keys):
                keyset_value = duplicate.keyset_value
                duplicate_pks = duplicate.duplicate_pks
                _logger.info(f"Duplicates found: {pulp_type=}; {keyset_value=}; {duplicate_pks=}")
    if dup_found:
        raise DuplicateContentInRepositoryError(dup_count, correlation_id)


class DuplicateEntry(NamedTuple):
    keyset_value: tuple[str, ...]
    duplicate_pks: list[str]


def count_duplicates(content_qs, unique_keys: tuple[str]) -> int:
    new_content_total = content_qs.count()
    unique_new_content_total = content_qs.distinct(*unique_keys).count()
    return new_content_total - unique_new_content_total


def collect_duplicates(content_qs, unique_keys: tuple[str]) -> list[DuplicateEntry]:
    last_keyset = None
    last_pk = None
    keyset_to_contents = defaultdict(list)
    content_qs = content_qs.values_list(*unique_keys, "pk")
    for values in content_qs.order_by(*unique_keys).iterator():
        keyset_value = values[:-1]
        pk = str(values[-1])
        if keyset_value == last_keyset:
            dup_pk_list = keyset_to_contents[keyset_value]
            # the previous duplicate didn't know it was a duplicate
            if len(dup_pk_list) == 0:
                dup_pk_list.append(last_pk)
            dup_pk_list.append(pk)
        last_keyset = keyset_value
        last_pk = pk
    duplicate_entries = []
    for keyset_value, pk_list in keyset_to_contents.items():
        duplicate_entries.append(DuplicateEntry(duplicate_pks=pk_list, keyset_value=keyset_value))
    return duplicate_entries


def validate_version_paths(version):
    """
    Validate artifact relative paths for dupes or overlap (e.g. a/b and a/b/c).

    Raises:
        ValueError: If two artifact relative paths overlap
    """
    # Get unique (path, artifact) pairs to allow artifacts shared across content
    content_artifacts = (
        ContentArtifact.objects.filter(content__pk__in=version.content)
        .values_list("relative_path", "artifact")
        .distinct()
    )

    paths = [path for path, artifact_id in content_artifacts]

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
