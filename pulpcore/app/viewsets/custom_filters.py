"""
This module contains custom filters that might be used by more than one ViewSet.
"""
import re
from gettext import gettext as _
from urllib.parse import urlparse
from uuid import UUID

from django.urls import Resolver404, resolve
from django_filters import BaseInFilter, CharFilter, DateTimeFilter, Filter
from django_filters.fields import IsoDateTimeField
from rest_framework import serializers
from rest_framework.serializers import ValidationError as DRFValidationError

from pulpcore.app.models import ContentArtifact, Label, RepositoryVersion
from pulpcore.app.viewsets import NamedModelViewSet


class ReservedResourcesFilter(Filter):
    """
    Enables a user to filter tasks by a reserved resource href
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


class HyperlinkRelatedFilter(Filter):
    """
    Enables a user to filter by a foreign key using that FK's href
    """

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("help_text", _("Foreign Key referenced by HREF"))
        super().__init__(*args, **kwargs)

    def filter(self, qs, value):
        """
        Args:
            qs (django.db.models.query.QuerySet): The Queryset to filter
            value (string): href containing pk for the foreign key instance

        Returns:
            django.db.models.query.QuerySet: Queryset filtered by the foreign key pk
        """

        if value is None:
            # value was not supplied by the user
            return qs

        if not value:
            raise serializers.ValidationError(
                detail=_("No value supplied for {name} filter.").format(name=self.field_name)
            )
        try:
            match = resolve(urlparse(value).path)
        except Resolver404:
            raise serializers.ValidationError(detail=_("URI not valid: {u}").format(u=value))

        pk = match.kwargs["pk"]
        try:
            UUID(pk, version=4)
        except ValueError:
            raise serializers.ValidationError(detail=_("UUID invalid: {u}").format(u=pk))

        key = "{}__pk".format(self.field_name)
        return qs.filter(**{key: pk})


class IsoDateTimeFilter(DateTimeFilter):
    """
    Uses IsoDateTimeField to support filtering on ISO 8601 formated datetimes.
    For context see:
    * https://code.djangoproject.com/ticket/23448
    * https://github.com/tomchristie/django-rest-framework/issues/1338
    * https://github.com/alex/django-filter/pull/264
    """

    field_class = IsoDateTimeField

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("help_text", _("ISO 8601 formatted dates are supported"))
        super().__init__(*args, **kwargs)


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


class LabelSelectFilter(Filter):
    """Filter to get resources that match a label filter string."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("help_text", _("Filter labels by search string"))
        super().__init__(*args, **kwargs)

    def filter(self, qs, value):
        """
        Args:
            qs (django.db.models.query.QuerySet): The Model queryset
            value (string): label search querry

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
