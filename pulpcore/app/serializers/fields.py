import hashlib
import os
from gettext import gettext as _

from django.conf import settings
from rest_framework import serializers
from rest_framework.fields import empty
from rest_framework.reverse import reverse
from rest_framework_nested.relations import NestedHyperlinkedRelatedField

from pulpcore.app import models
from pulpcore.app.serializers import DetailRelatedField, RelatedField


def relative_path_validator(relative_path):
    if os.path.isabs(relative_path):
        raise serializers.ValidationError(_("Relative path can't start with '/'. "
                                            "{0}").format(relative_path))


class ContentRelatedField(DetailRelatedField):
    """
    Serializer Field for use when relating to Content Detail Models
    """
    queryset = models.Content.objects.all()


class SingleContentArtifactField(RelatedField):
    """
    A serializer field for the '_artifacts' ManyToManyField on the Content model (single-artifact).
    """
    lookup_field = 'pk'
    view_name = 'artifacts-detail'
    queryset = models.Artifact.objects.all()
    allow_null = True

    def get_attribute(self, instance):
        """
        Returns the field from the instance that should be serialized using this serializer field.

        This serializer looks up the list of artifacts and returns only one, if any exist. If more
        than one exist, it throws and exception because this serializer is being used in an
        improper context.

        Args:
            instance (:class:`pulpcore.app.models.Content`): An instance of Content being
                serialized.

        Returns:
            A single Artifact model related to the instance of Content.
        """
        # using get() and first() will query the db. count() and all() will use cached artifacts if
        # they are prefetched.
        if instance._artifacts.count() == 0:
            return None
        if instance._artifacts.count() == 1:
            return instance._artifacts.all()[0]
        if instance._artifacts.count() > 1:
            raise ValueError(_("SingleContentArtifactField should not be used in a context where "
                               "multiple artifacts for one content is possible."))


class ContentArtifactChecksumField(serializers.CharField):
    """
    A serializer field for the artifact checksum Content model (single-artifact).
    """

    def __init__(self, *args, **kwargs):
        kwargs['read_only'] = True
        self.checksum = kwargs.pop('checksum', 'md5')
        super().__init__(*args, **kwargs)

    def get_attribute(self, instance):
        """
        Returns the field from the instance that should be serialized using this serializer field.

        This serializer looks up the checksum for single artifact content

        Args:
            instance (:class:`pulpcore.app.models.Content`): An instance of Content being
                serialized.

        Returns:
            A string of the checksum or None.

        Raises:
            :class:`rest_framework.exceptions.ValidationError`: When more than one Artifacts exist.
        """
        # using get() and first() will query the db. count() and all() will use cached artifacts if
        # they are prefetched.
        if instance._artifacts.count() == 0:
            return None
        if instance._artifacts.count() == 1:
            return getattr(instance._artifacts.all()[0], self.checksum)
        if instance._artifacts.count() > 1:
            raise ValueError(_("ContentArtifactChecksumField should not be used in a context where "
                               "multiple artifacts for one content is possible."))


class ContentArtifactsField(serializers.DictField):
    """
    A serializer field for the '_artifacts' ManyToManyField on the Content model.
    """

    def run_validation(self, data):
        """
        Validates 'data' dict.

        Validates that all keys of 'data' are relative paths. Validates that all values of 'data'
        are URLs for an existing Artifact.

        Args:
            data (dict): A dict mapping relative paths inside the Content to the corresponding
                Artifact URLs.

        Returns:
            A dict mapping relative paths inside the Content to the corresponding Artifact
                instances.

        Raises:
            :class:`rest_framework.exceptions.ValidationError`: When one of the Artifacts does not
                exist or one of the paths is not a relative path or the field is missing.
        """
        ret = {}
        if data is empty:
            raise serializers.ValidationError(_('artifacts field must be specified.'))
        for relative_path, url in data.items():
            relative_path_validator(relative_path)
            artifactfield = RelatedField(view_name='artifacts-detail',
                                         queryset=models.Artifact.objects.all(),
                                         source='*', initial=url)
            try:
                artifact = artifactfield.run_validation(data=url)
                ret[relative_path] = artifact
            except serializers.ValidationError as e:
                # Append the URL of missing Artifact to the error message
                e.detail[0] = "%s %s" % (e.detail[0], url)
                raise e
        return ret

    def get_attribute(self, instance):
        """
        Returns the field from the instance that should be serialized using this serializer field.

        This serializer field serializes a ManyToManyField that is actually stored as a
        ContentArtifact model. Instead of returning the field, this method returns all the
        ContentArtifact models related to this Content.

        Args:
            instance (:class:`pulpcore.app.models.Content`): An instance of Content being
                serialized.

        Returns:
            A list of ContentArtifact models related to the instance of Content.
        """
        return instance.contentartifact_set.all()

    def to_representation(self, value):
        """
        Serializes list of ContentArtifacts.

        Returns a dict mapping relative paths inside the Content to the corresponding Artifact
        URLs.

        Args:
            value (list of :class:`pulpcore.app.models.ContentArtifact`): A list of all the
                ContentArtifacts related to the Content model being serialized.

        Returns:
            A dict where keys are relative path of the artifact inside the Content and values are
                Artifact URLs.
        """
        ret = {}
        for content_artifact in value:
            if content_artifact.artifact_id:
                url = reverse('artifacts-detail', kwargs={'pk': content_artifact.artifact_id},
                              request=None)
            else:
                url = None
            ret[content_artifact.relative_path] = url
        return ret


class LatestVersionField(NestedHyperlinkedRelatedField):
    parent_lookup_kwargs = {'repository_pk': 'repository__pk'}
    lookup_field = 'number'
    view_name = 'versions-detail'

    def __init__(self, *args, **kwargs):
        """
        Unfortunately you can't just set read_only=True on the class. It has
        to be done explicitly in the kwargs to __init__, or else DRF complains.
        """
        kwargs['read_only'] = True
        super().__init__(*args, **kwargs)

    def get_url(self, obj, view_name, request, format):
        """
        Returns the URL for the appropriate object. Overrides the DRF method to change how the
        object is found.

        Args:
            obj (list of :class:`pulpcore.app.models.RepositoryVersion`): The versions of the
                current viewset's repository.
            view_name (str): The name of the view that should be used.
            request (rest_framework.request.Request): the current HTTP request being handled
            format: undocumented by DRF. ???

        Returns:
            str: the URL corresponding to the latest version of the current repository. If there
                are no versions, returns None
        """
        try:
            version = obj.exclude(complete=False).latest()
        except obj.model.DoesNotExist:
            return None

        kwargs = {
            'repository_pk': version.repository.pk,
            'number': version.number,
        }
        return self.reverse(view_name, kwargs=kwargs, request=None, format=format)

    def get_attribute(self, instance):
        """
        Args:
            instance (pulpcore.app.models.Repository): a repository that has been matched by the
                current ViewSet.

        Returns:
            list of :class:`pulpcore.app.models.RepositoryVersion`

        """
        return instance.versions


class BaseURLField(serializers.CharField):
    """
    Serializer Field for the base_url field of the Distribution.
    """

    def to_representation(self, value):
        base_path = value
        host = settings.CONTENT_HOST
        prefix = settings.CONTENT_PATH_PREFIX
        return '/'.join(
            (
                host.strip('/'),
                prefix.strip('/'),
                base_path.lstrip('/')
            ))


class SecretCharField(serializers.CharField):
    """
    Serializer field for secrets.

    This field accepts text as input and it returns a sha256 digest of the text stored.
    """

    def to_representation(self, value):
        return hashlib.sha256(bytes(value, 'utf-8')).hexdigest()
