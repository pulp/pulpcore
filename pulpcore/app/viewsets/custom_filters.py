"""
This module contains custom filters that might be used by more than one ViewSet.
"""

import re

from collections import defaultdict
from itertools import chain
from gettext import gettext as _

from django.conf import settings
from pulpcore.constants import LABEL_KEY_CHARS
from django.db.models import Q
from django_filters import BaseInFilter, CharFilter, Filter
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework.serializers import ValidationError as DRFValidationError

from pulpcore.app.models import Content, ContentArtifact, Repository, RepositoryVersion
from pulpcore.app.viewsets import NamedModelViewSet
from pulpcore.app.util import get_prn, get_domain_pk, extract_pk, raise_for_unknown_content_units

# Lookup conversion table from old resource hrefs to new PDRN resource names
OLD_RESOURCE_HREFS = {
    "/api/v3/orphans/cleanup/": "orphans",
    "/api/v3/repair/": "repair",
    "/api/v3/distributions/": "distributions",
    "/api/v3/repositories/reclaim_space/": "reclaim_space",
    "/api/v3/servers/": "servers",
}


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
            value (string|List[str]): href/prn to a reserved resource or a list thereof

        Returns:
            django.db.models.query.QuerySet: Queryset filtered by the reserved resource
        """

        if value is not None:
            if isinstance(value, str):
                value = [value]
            # Ensure passing hrefs still works as valid filterable
            for i, item in enumerate(value):
                if item.startswith(settings.API_ROOT):
                    try:
                        prn = get_prn(uri=item)
                    except DRFValidationError:
                        pass
                    else:
                        value[i] = prn
                elif item in OLD_RESOURCE_HREFS:
                    value[i] = f"pdrn:{get_domain_pk()}:{OLD_RESOURCE_HREFS[item]}"
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

        resource = NamedModelViewSet.get_resource(value)

        return qs.filter(created_resources__object_id=resource.pk)


@extend_schema_field(OpenApiTypes.STR)
class RepoVersionHrefPrnFilter(Filter):
    """
    Filter Content by a Repository Version.
    """

    def __init__(self, *args, **kwargs):
        kwargs.setdefault(
            "help_text",
            _(
                "Repository Version referenced by HREF/PRN or Repository HREF/PRN"
                " (choose latest version)"
            ),
        )
        super().__init__(*args, **kwargs)

    @staticmethod
    def get_repository_version(value):
        """
        Get the repository version from the HREF/PRN value provided by the user.

        Args:
            value (string): The RepositoryVersion href/prn to filter by
        """
        if not value:
            raise serializers.ValidationError(
                detail=_("No value supplied for repository version filter")
            )

        object = NamedModelViewSet.get_resource(value)
        if isinstance(object, Repository):
            object = object.latest_version()
        if not isinstance(object, RepositoryVersion):
            raise serializers.ValidationError(
                detail=_("URI {u} not found for {m}.").format(u=value, m="repositoryversion")
            )
        return object

    def filter(self, qs, value):
        """
        Args:
            qs (django.db.models.query.QuerySet): The Content Queryset
            value (string): The RepositoryVersion href/prn to filter by
        """
        raise NotImplementedError()


class RepositoryVersionFilter(RepoVersionHrefPrnFilter):
    """
    Filter by RepositoryVersion href/prn.
    """

    def filter(self, qs, value):
        """
        Args:
            qs (django.db.models.query.QuerySet): The Queryset to filter
            value (string): The RepositoryVersion href/prn to filter by

        Returns:
            Queryset filtered by given repository version on field_name
        """
        if value is None:
            # user didn't supply a value
            return qs

        repo_version = self.get_repository_version(value)
        key = f"{self.field_name}__pk"
        return qs.filter(**{key: repo_version.pk})


class ArtifactRepositoryVersionFilter(RepoVersionHrefPrnFilter):
    """
    Filter used to get the artifacts in a repository version.
    """

    def filter(self, qs, value):
        """
        Args:
            qs (django.db.models.query.QuerySet): The Artifact Queryset
            value (string): The RepositoryVersion href/prn to filter by

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


class ContentRepositoryVersionFilter(RepoVersionHrefPrnFilter):
    """
    Filter used to get the content of this type found in a repository version.
    """

    def filter(self, qs, value):
        """
        Args:
            qs (django.db.models.query.QuerySet): The Content Queryset
            value (string): The RepositoryVersion href/prn to filter by

        Returns:
            Queryset of the content contained within the specified repository version
        """
        if value is None:
            # user didn't supply a value
            return qs

        repo_version = self.get_repository_version(value)
        return qs.filter(pk__in=repo_version.content)


class ContentAddedRepositoryVersionFilter(RepoVersionHrefPrnFilter):
    """
    Filter used to get the content of this type found in a repository version.
    """

    def filter(self, qs, value):
        """
        Args:
            qs (django.db.models.query.QuerySet): The Content Queryset
            value (string): The RepositoryVersion href/prn to filter by

        Returns:
            Queryset of the content added by the specified repository version
        """
        if value is None:
            # user didn't supply a value
            return qs

        repo_version = self.get_repository_version(value)
        return qs.filter(pk__in=repo_version.added())


class ContentRemovedRepositoryVersionFilter(RepoVersionHrefPrnFilter):
    """
    Filter used to get the content of this type found in a repository version.
    """

    def filter(self, qs, value):
        """
        Args:
            qs (django.db.models.query.QuerySet): The Content Queryset
            value (string): The RepositoryVersion href/prn to filter by

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
        if "label_field_name" in kwargs:
            self.label_field_name = kwargs.pop("label_field_name")
        else:
            self.label_field_name = "pulp_labels"
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

        # NOTE: can't use self.field_name because the default for that is the name
        # of the method on the filter class (which is pulp_label_select on all of
        # the pulp filtersets)
        field_name = self.label_field_name
        if value is None:
            # user didn't supply a value
            return qs

        for term in value.split(","):
            match = re.match(rf"(!?{LABEL_KEY_CHARS}+)(=|!=|~)?(.*)?", term)
            if not match:
                raise DRFValidationError(_("Invalid search term: '{}'.").format(term))
            key, op, val = match.groups()

            if key.startswith("!") and op:
                raise DRFValidationError(_("Cannot use an operator with '{}'.").format(key))

            if op == "=":
                qs = qs.filter(**{f"{field_name}__contains": {key: val}})
            elif op == "!=":
                qs = qs.filter(**{f"{field_name}__has_key": key}).exclude(
                    **{f"{field_name}__contains": {key: val}}
                )
            elif op == "~":
                qs = qs.filter(**{f"{field_name}__{key}__icontains": val})
            else:
                # 'foo', '!foo'
                if key.startswith("!"):
                    qs = qs.exclude(**{f"{field_name}__has_key": key[1:]})
                else:
                    qs = qs.filter(**{f"{field_name}__has_key": key})

        return qs


class WithContentFilter(Filter):
    """Filter class for filtering by content in Publications and RepositoryVersions."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("help_text", _("Content Unit referenced by HREF/PRN"))
        super().__init__(*args, **kwargs)

    def filter(self, qs, value):
        """
        Args:
            qs (django.db.models.query.QuerySet): The Publication/RepositoryVersion Queryset
            value (string or list[string]): of content href/prn(s) to filter

        Returns:
            Queryset of the Publication/RepositoryVersion containing the specified content
        """
        if value is None:
            # user didn't supply a value
            return qs

        if not value:
            raise serializers.ValidationError(detail=_("No value supplied for content filter"))

        if isinstance(value, str):
            value = [value]

        content_units = {}
        for url in value:
            content_units[extract_pk(url)] = url

        content_units_pks = set(content_units.keys())
        existing_content_units = Content.objects.filter(pk__in=content_units_pks)
        raise_for_unknown_content_units(existing_content_units, content_units)

        return qs.with_content(content_units_pks)


class WithContentInFilter(BaseInFilter, WithContentFilter):
    """The multi-content variant of WithContentFilter."""


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

        for dist in qs.filter(
            Q(publication__isnull=False)
            | Q(repository__isnull=False)
            | Q(repository_version__isnull=False)
        ):
            _repo, repo_version, publication = dist.get_repository_publication_and_version()
            if repo_version and (publication or not dist.detail_model.SERVE_FROM_PUBLICATION):
                versions_distributions[repo_version.pk].append(dist.pk)

        content = NamedModelViewSet.get_resource(value)
        versions = RepositoryVersion.objects.with_content([content.pk]).values_list("pk", flat=True)

        distributions = chain.from_iterable(versions_distributions[version] for version in versions)
        return qs.filter(pk__in=distributions)
