from collections import defaultdict
from gettext import gettext as _
import logging

from django.db.models import Q


_logger = logging.getLogger(__name__)


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
    query_for_repo_duplicates_by_type = defaultdict(lambda: Q())
    for item in repository_version.added():
        detail_item = item.cast()
        if detail_item.repo_key_fields == ():
            continue
        unit_q_dict = {
            field: getattr(detail_item, field) for field in detail_item.repo_key_fields
        }
        item_query = Q(**unit_q_dict) & ~Q(pk=detail_item.pk)
        query_for_repo_duplicates_by_type[detail_item._meta.model] |= item_query

    for model in query_for_repo_duplicates_by_type:
        _logger.debug(_("Removing duplicates for type: {}".format(model)))
        qs = model.objects.filter(query_for_repo_duplicates_by_type[model])
        repository_version.remove_content(qs)
