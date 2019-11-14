from gettext import gettext as _
from logging import getLogger

from django.db import transaction

from pulpcore.app import models, serializers

log = getLogger(__name__)


def delete(repo_id):
    """
    Delete a :class:`~pulpcore.app.models.Repository`

    Args:
        repo_id (int): The name of the repository to be deleted
    """

    models.Repository.objects.filter(pk=repo_id).delete()


def update(repo_id, partial=True, data=None):
    """
    Updates a :class:`~pulpcore.app.models.Repository`

    Args:
        repo_id (int): The id of the repository to be updated
        partial (bool): Boolean to allow partial updates. If set to False, values for all
                        required fields must be passed or a validation error will be raised.
                        Defaults to True
        data (QueryDict): dict of attributes to change and their new values; if None, no attempt to
                     update the repository object will be made
    """
    instance = models.Repository.objects.get(pk=repo_id)
    serializer = serializers.RepositorySerializer(instance, data=data, partial=partial)
    serializer.is_valid(raise_exception=True)
    serializer.save()


def delete_version(pk):
    """
    Delete a repository version by squashing its changes with the next newer version. This ensures
    that the content set for each version stays the same.

    There must be a newer version to squash into. If we deleted the latest version, the next content
    change would create a new one of the same number, which would violate the immutability
    guarantee.

    Args:
        pk (int): the primary key for a RepositoryVersion to delete

    Raises:
        models.RepositoryVersion.DoesNotExist: if there is not a newer version to squash into.
            TODO: something more friendly
    """
    with transaction.atomic():
        try:
            version = models.RepositoryVersion.objects.get(pk=pk)
        except models.RepositoryVersion.DoesNotExist:
            log.info(_('The repository version was not found. Nothing to do.'))
            return

        log.info(_('Deleting and squashing version %(v)d of repository %(r)s'),
                 {'v': version.number, 'r': version.repository.name})

        version.delete()


def add_and_remove(repository_pk, add_content_units, remove_content_units, base_version_pk=None):
    """
    Create a new repository version by adding and then removing content units.

    Args:
        repository_pk (int): The primary key for a Repository for which a new Repository Version
            should be created.
        add_content_units (list): List of PKs for :class:`~pulpcore.app.models.Content` that
            should be added to the previous Repository Version for this Repository.
        remove_content_units (list): List of PKs for:class:`~pulpcore.app.models.Content` that
            should be removed from the previous Repository Version for this Repository.
        base_version_pk (int): the primary key for a RepositoryVersion whose content will be used
            as the initial set of content for our new RepositoryVersion
    """
    repository = models.Repository.objects.get(pk=repository_pk).cast()

    if base_version_pk:
        base_version = models.RepositoryVersion.objects.get(pk=base_version_pk)
    else:
        base_version = None

    if '*' in remove_content_units:
        latest = repository.latest_version()
        if latest:
            remove_content_units = latest.content.values_list('pk', flat=True)
        else:
            remove_content_units = []

    with repository.new_version(base_version=base_version) as new_version:
        new_version.remove_content(models.Content.objects.filter(pk__in=remove_content_units))
        new_version.add_content(models.Content.objects.filter(pk__in=add_content_units))
