"""
This module contains custom filters that might be used by more than one ViewSet.
"""
from gettext import gettext as _
from urllib.parse import urlparse

from django.urls import resolve, Resolver404
from django_filters import Filter, DateTimeFilter
from django_filters.fields import IsoDateTimeField

from rest_framework import serializers
from uuid import UUID

from pulpcore.app.models import RepositoryVersion
from pulpcore.app.viewsets import NamedModelViewSet


class HyperlinkRelatedFilter(Filter):
    """
    Enables a user to filter by a foreign key using that FK's href
    """

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('help_text', _('Foreign Key referenced by HREF'))
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
                detail=_('No value supplied for {name} filter.').format(name=self.field_name))
        try:
            match = resolve(urlparse(value).path)
        except Resolver404:
            raise serializers.ValidationError(detail=_('URI not valid: {u}').format(u=value))

        pk = match.kwargs['pk']
        try:
            UUID(pk, version=4)
        except ValueError:
            raise serializers.ValidationError(detail=_('UUID invalid: {u}').format(u=pk))

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
        kwargs.setdefault('help_text', _('ISO 8601 formatted dates are supported'))
        super().__init__(*args, **kwargs)


class RepoVersionHrefFilter(Filter):
    """
    Filter Content by a Repository Version.
    """

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('help_text', _('Repository Version referenced by HREF'))
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
                detail=_('No value supplied for repository version filter'))

        return NamedModelViewSet.get_resource(value, RepositoryVersion)

    def filter(self, qs, value):
        """
        Args:
            qs (django.db.models.query.QuerySet): The Content Queryset
            value (string): The RepositoryVersion href to filter by
        """
        raise NotImplementedError()


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
