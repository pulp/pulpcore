"""
This module contains custom filters that might be used by more than one ViewSet.
"""
import re

from collections import defaultdict
from itertools import chain
from gettext import gettext as _
from urllib.parse import urlparse

from django.urls import Resolver404, resolve
from django.db.models import ObjectDoesNotExist
from django_filters import BaseInFilter, CharFilter, Filter
from rest_framework import serializers
from rest_framework.serializers import ValidationError as DRFValidationError

from pulpcore.app.models import ContentArtifact, Label, RepositoryVersion, Publication
from pulpcore.app.viewsets import NamedModelViewSet
from pulpcore.app.loggers import deprecation_logger


class ReservedResourcesFilter(Filter):
    """
    Enables a user to filter tasks by a reserved resource href.
    """

    def __init__(self, *args, exclusive=True, shared=True, **kwargs):
        self.exclusive = exclusive
        self.shared = shared
        assert (
            exclusive or shared
        ), "ReservedResourceFilter must have either exclusive or shared set."
        super().__init__(*args, **kwargs)

    def filter(self, qs, value):
        """
        Callback to filter the query set based on the provided filter value.

        Args:
            qs (django.db.models.query.QuerySet): The Queryset to filter
            value (string|List[str]): href to a reference to a reserved resource or a list thereof

        Returns:
            django.db.models.query.QuerySet: Queryset filtered by the reserved resource
        """

        if value is not None:
            if isinstance(value, str):
                value = [value]
            if self.exclusive:
                if self.shared:
                    for item in value:
                        qs = qs.filter(reserved_resources_record__overlap=[item, "shared:" + item])
                else:
                    qs = qs.filter(reserved_resources_record__contains=value)
            else:  # self.shared
                qs = qs.filter(
                    reserved_resources_record__contains=["shared:" + item for item in value]
                )

        return qs


class ReservedResourcesInFilter(BaseInFilter, ReservedResourcesFilter):
    """
    Enables a user to filter tasks by a list of reserved resource hrefs.
    """


class ReservedResourcesRecordFilter(Filter):
    """
    Enables a user to filter tasks by a reserved resource href.

    Warning: This filter is badly documented and not fully functional, but we need to keep it for
    compatibility reasons. Use ``ReservedResourcesFilter`` instead.
    """

    def filter(self, qs, value):
        """
        Args:
            qs (django.db.models.query.QuerySet): The Queryset to filter
            value (string): href containing a reference to a reserved resource

        Returns:
            django.db.models.query.QuerySet: Queryset filtered by the reserved resource
        """

        if value is None:
            # a value was not supplied by a user
            return qs

        try:
            resolve(urlparse(value).path)
        except Resolver404:
            raise serializers.ValidationError(detail=_("URI not valid: {u}").format(u=value))

        return qs.filter(reserved_resources_record__contains=[value])


class CreatedResourcesFilter(Filter):
    """
    Filter used to get tasks by created resources.

    Created resources contain a reference to newly created repository
    versions, distributions, etc.
    """

    def filter(self, qs, value):
        """
        Args:
            qs (django.db.models.query.QuerySet): The QuerySet to filter
            value (string): The content href to filter by

        Returns:
            Queryset of the content contained within the specified created resource
        """

        if value is None:
            return qs

        match = resolve(value)
        resource = NamedModelViewSet.get_resource(value, match.func.cls.queryset.model)

        return qs.filter(created_resources__object_id=resource.pk)


class RepoVersionHrefFilter(Filter):
    """
    Filter Content by a Repository Version.
    """

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("help_text", _("Repository Version referenced by HREF"))
        super().__init__(*args, **kwargs)

    @staticmethod
    def get_repository_version(value):
        """
        Get the repository version from the HREF value provided by the user.

        Args:
            value (string): The RepositoryVersion href to filter by
        """
        if not value:
            raise serializers.ValidationError(
                detail=_("No value supplied for repository version filter")
            )

        return NamedModelViewSet.get_resource(value, RepositoryVersion)

    def filter(self, qs, value):
        """
        Args:
            qs (django.db.models.query.QuerySet): The Content Queryset
            value (string): The RepositoryVersion href to filter by
        """
        raise NotImplementedError()


class RepositoryVersionFilter(RepoVersionHrefFilter):
    """
    Filter by RepositoryVersion href.
    """

    def filter(self, qs, value):
        """
        Args:
            qs (django.db.models.query.QuerySet): The Queryset to filter
            value (string): The RepositoryVersion href to filter by

        Returns:
            Queryset filtered by given repository version on field_name
        """
        if value is None:
            # user didn't supply a value
            return qs

        repo_version = self.get_repository_version(value)
        key = f"{self.field_name}__pk"
        return qs.filter(**{key: repo_version.pk})


class ArtifactRepositoryVersionFilter(RepoVersionHrefFilter):
    """
    Filter used to get the artifacts in a repository version.
    """

    def filter(self, qs, value):
        """
        Args:
            qs (django.db.models.query.QuerySet): The Artifact Queryset
            value (string): The RepositoryVersion href to filter by

        Returns:
            Queryset of the artifacts contained within the specified repository version
        """
        if value is None:
            # user didn't supply a value
            return qs

        repo_version = self.get_repository_version(value)
        content = repo_version.content
        artifact_pks = ContentArtifact.objects.filter(content__in=content).values("artifact__pk")
        return qs.filter(pk__in=artifact_pks)


class ContentRepositoryVersionFilter(RepoVersionHrefFilter):
    """
    Filter used to get the content of this type found in a repository version.
    """

    def filter(self, qs, value):
        """
        Args:
            qs (django.db.models.query.QuerySet): The Content Queryset
            value (string): The RepositoryVersion href to filter by

        Returns:
            Queryset of the content contained within the specified repository version
        """
        if value is None:
            # user didn't supply a value
            return qs

        repo_version = self.get_repository_version(value)
        return qs.filter(pk__in=repo_version.content)


class ContentAddedRepositoryVersionFilter(RepoVersionHrefFilter):
    """
    Filter used to get the content of this type found in a repository version.
    """

    def filter(self, qs, value):
        """
        Args:
            qs (django.db.models.query.QuerySet): The Content Queryset
            value (string): The RepositoryVersion href to filter by

        Returns:
            Queryset of the content added by the specified repository version
        """
        if value is None:
            # user didn't supply a value
            return qs

        repo_version = self.get_repository_version(value)
        return qs.filter(pk__in=repo_version.added())


class ContentRemovedRepositoryVersionFilter(RepoVersionHrefFilter):
    """
    Filter used to get the content of this type found in a repository version.
    """

    def filter(self, qs, value):
        """
        Args:
            qs (django.db.models.query.QuerySet): The Content Queryset
            value (string): The RepositoryVersion href to filter by

        Returns:
            Queryset of the content removed by the specified repository version
        """
        if value is None:
            # user didn't supply a value
            return qs

        repo_version = self.get_repository_version(value)
        return qs.filter(pk__in=repo_version.removed())


class CharInFilter(BaseInFilter, CharFilter):
    pass


class LabelFilter(Filter):
    """Filter to get resources that match a label filter string."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("help_text", _("Filter labels by search string"))
        super().__init__(*args, **kwargs)

    def filter(self, qs, value):
        """
        Args:
            qs (django.db.models.query.QuerySet): The Model queryset
            value (string): label search query

        Returns:
            Queryset of the Models filtered by label(s)

        Raises:
            rest_framework.exceptions.ValidationError: on invalid search string
        """
        if value is None:
            # user didn't supply a value
            return qs

        for term in value.split(","):
            match = re.match(r"(!?[\w\s]+)(=|!=|~)?(.*)?", term)
            if not match:
                raise DRFValidationError(_("Invalid search term: '{}'.").format(term))
            key, op, val = match.groups()

            if key.startswith("!") and op:
                raise DRFValidationError(_("Cannot use an operator with '{}'.").format(key))

            if op == "=":
                qs = qs.filter(**{f"pulp_labels__{key}": val})
            elif op == "!=":
                qs = qs.filter(pulp_labels__has_key=key).exclude(**{f"pulp_labels__{key}": val})
            elif op == "~":
                qs = qs.filter(**{f"pulp_labels__{key}__icontains": val})
            else:
                # 'foo', '!foo'
                if key.startswith("!"):
                    qs = qs.exclude(pulp_labels__has_key=key[1:])
                else:
                    qs = qs.filter(pulp_labels__has_key=key)

        return qs


class LabelSelectFilter(Filter):
    """Filter to get resources that match a label filter string. DEPRECATED."""

    def __init__(self, *args, **kwargs):
        deprecation_logger.warning(
            "'LabelSelectFilter' is deprecated and will be removed in pulpcore==3.25;"
            " use 'LabelFilter' instead."
        )
        super().__init__(*args, **kwargs)

        kwargs.setdefault("help_text", _("Filter labels by search string"))
        super().__init__(*args, **kwargs)

    def filter(self, qs, value):
        """
        Args:
            qs (django.db.models.query.QuerySet): The Model queryset
            value (string): label search query

        Returns:
            Queryset of the Models filtered by label(s)

        Raises:
            rest_framework.exceptions.ValidationError: on invalid search string
        """
        if value is None:
            # user didn't supply a value
            return qs

        for term in value.split(","):
            match = re.match(r"(!?[\w\s]+)(=|!=|~)?(.*)?", term)
            if not match:
                raise DRFValidationError(_("Invalid search term: '{}'.").format(term))
            key, op, val = match.groups()

            if key.startswith("!") and op:
                raise DRFValidationError(_("Cannot use an operator with '{}'.").format(key))

            if op == "=":
                labels = Label.objects.filter(key=key, value=val)
                qs = qs.filter(pulp_labels__in=labels)
            elif op == "!=":
                labels = Label.objects.filter(key=key).exclude(value=val)
                qs = qs.filter(pulp_labels__in=labels)
            elif op == "~":
                labels = Label.objects.filter(key=key, value__icontains=val)
                qs = qs.filter(pulp_labels__in=labels)
            else:
                # 'foo', '!foo'
                if key.startswith("!"):
                    labels = Label.objects.filter(key=key[1:])
                    qs = qs.exclude(pulp_labels__in=labels)
                else:
                    labels = Label.objects.filter(key=key)
                    qs = qs.filter(pulp_labels__in=labels)

        return qs


class DistributionWithContentFilter(Filter):
    """A Filter class enabling filtering by content units served by distributions."""

    def __init__(self, *args, **kwargs):
        """Initialize a help message for the filter."""
        kwargs.setdefault(
            "help_text", _("Filter distributions based on the content served by them")
        )
        super().__init__(*args, **kwargs)

    def filter(self, qs, value):
        """Filter distributions by the provided content unit."""
        if value is None:
            return qs

        # the same repository version can be referenced from multiple distributions; therefore,
        # we are later appending distributions to a list value representing a single repository
        # version
        versions_distributions = defaultdict(list)

        for dist in qs.exclude(publication=None).values("publication__repository_version", "pk"):
            versions_distributions[dist["publication__repository_version"]].append(dist["pk"])

        for dist in qs.exclude(repository_version=None).values("repository_version", "pk"):
            if not dist.cast().SERVE_FROM_PUBLICATION:
                versions_distributions[dist["repository_version"]].append(dist["pk"])

        for dist in qs.exclude(repository=None).prefetch_related("repository__versions"):
            if dist.cast().SERVE_FROM_PUBLICATION:
                versions = dist.repository.versions.values_list("pk", flat=True)
                publications = Publication.objects.filter(
                    repository_version__in=versions, complete=True
                )

                try:
                    publication = publications.select_related("repository_version").latest(
                        "repository_version", "pulp_created"
                    )
                except ObjectDoesNotExist:
                    pass
                else:
                    repo_version = publication.repository_version
                    versions_distributions[repo_version.pk].append(dist.pk)
            else:
                repo_version = dist.repository.latest_version()
                versions_distributions[repo_version.pk].append(dist.pk)

        content = NamedModelViewSet.get_resource(value)
        versions = RepositoryVersion.objects.with_content([content.pk]).values_list("pk", flat=True)

        distributions = chain.from_iterable(versions_distributions[version] for version in versions)
        return qs.filter(pk__in=distributions)
