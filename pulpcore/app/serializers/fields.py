import os
from gettext import gettext as _

from django.conf import settings
from rest_framework import serializers
from rest_framework.fields import empty
from rest_framework.reverse import reverse

from pulpcore.app import models
from pulpcore.app.serializers import DetailIdentityField, IdentityField, RelatedField


def relative_path_validator(relative_path):
    if os.path.isabs(relative_path):
        raise serializers.ValidationError(
            _("Relative path can't start with '/'. " "{0}").format(relative_path)
        )


class SingleContentArtifactField(RelatedField):
    """
    A serializer field for the '_artifacts' ManyToManyField on the Content model (single-artifact).
    """

    lookup_field = "pk"
    view_name = "artifacts-detail"
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
            raise ValueError(
                _(
                    "SingleContentArtifactField should not be used in a context where "
                    "multiple artifacts for one content is possible."
                )
            )


class ContentArtifactChecksumField(serializers.CharField):
    """
    A serializer field for the artifact checksum Content model (single-artifact).
    """

    def __init__(self, *args, **kwargs):
        kwargs["read_only"] = True
        self.checksum = kwargs.pop("checksum", "sha256")
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
            raise ValueError(
                _(
                    "ContentArtifactChecksumField should not be used in a context where "
                    "multiple artifacts for one content is possible."
                )
            )


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
            raise serializers.ValidationError(_("artifacts field must be specified."))
        for relative_path, url in data.items():
            relative_path_validator(relative_path)
            artifactfield = RelatedField(
                view_name="artifacts-detail",
                queryset=models.Artifact.objects.all(),
                source="*",
                initial=url,
            )
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
                url = reverse(
                    "artifacts-detail", kwargs={"pk": content_artifact.artifact_id}, request=None
                )
            else:
                url = None
            ret[content_artifact.relative_path] = url
        return ret


class RepositoryVersionsIdentityFromRepositoryField(DetailIdentityField):
    view_name = "repositories-detail"

    def __init__(self, view_name=None, **kwargs):
        assert view_name is None, "The `view_name` must not be set."
        super().__init__(view_name=self.view_name, **kwargs)

    def get_url(self, obj, view_name, request, *args, **kwargs):
        return super().get_url(obj, self.view_name, request, *args, **kwargs) + "versions/"


class RepositoryVersionFieldGetURLMixin:
    view_name = "versions-detail"

    def __init__(self, view_name=None, **kwargs):
        assert view_name is None, "The `view_name` must not be set."
        super().__init__(view_name=self.view_name, **kwargs)

    def get_url(self, obj, view_name, request, *args, **kwargs):
        rvr_field = RepositoryVersionsIdentityFromRepositoryField()
        repo_url = rvr_field.get_url(obj.repository, None, request, *args, **kwargs)
        return f"{repo_url}{obj.number}/"

    def use_pk_only_optimization(self):
        return False


class RepositoryVersionIdentityField(RepositoryVersionFieldGetURLMixin, IdentityField):
    pass


class RepositoryVersionRelatedField(RepositoryVersionFieldGetURLMixin, RelatedField):
    queryset = models.RepositoryVersion.objects.all()

    def get_object(self, view_name, view_args, view_kwargs):
        lookup_kwargs = {
            "repository__pk": view_kwargs["repository_pk"],
            "number": view_kwargs["number"],
        }
        return self.get_queryset().get(**lookup_kwargs)


class LatestVersionField(RepositoryVersionRelatedField):
    queryset = None  # read-only relational fields should not provide a `queryset` argument

    def __init__(self, *args, **kwargs):
        """
        Unfortunately you can't just set read_only=True on the class. It has
        to be done explicitly in the kwargs to __init__, or else DRF complains.
        """
        kwargs["read_only"] = True
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
        return super().get_url(version, view_name, request, format)

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
        origin = settings.CONTENT_ORIGIN.strip("/")
        prefix = settings.CONTENT_PATH_PREFIX.strip("/")
        base_path = value.strip("/")

        return "/".join((origin, prefix, base_path)) + "/"


class ExportsIdentityFromExporterField(DetailIdentityField):
    view_name = "exporters-detail"

    def __init__(self, view_name=None, **kwargs):
        assert view_name is None, "The `view_name` must not be set."
        super().__init__(view_name=self.view_name, **kwargs)

    def get_url(self, obj, view_name, request, *args, **kwargs):
        return super().get_url(obj, self.view_name, request, *args, **kwargs) + "exports/"


class ExportFieldGetURLMixin:
    view_name = "exports-detail"

    def __init__(self, view_name=None, **kwargs):
        assert view_name is None, "The `view_name` must not be set."
        super().__init__(view_name=self.view_name, **kwargs)

    def get_url(self, obj, view_name, request, *args, **kwargs):
        exports_field = ExportsIdentityFromExporterField()
        exporter_url = exports_field.get_url(obj.exporter, None, request, *args, **kwargs)
        return f"{exporter_url}{obj.pk}/"

    def use_pk_only_optimization(self):
        return False


class ExportIdentityField(ExportFieldGetURLMixin, IdentityField):
    pass


class ExportRelatedField(ExportFieldGetURLMixin, RelatedField):
    queryset = models.Export.objects.all()

    def get_object(self, view_name, view_args, view_kwargs):
        lookup_kwargs = {"exporter__pk": view_kwargs["exporter_pk"], "pk": view_kwargs["pk"]}
        return self.get_queryset().get(**lookup_kwargs)


class ImportsIdentityFromImporterField(DetailIdentityField):
    view_name = "importers-detail"

    def __init__(self, view_name=None, **kwargs):
        assert view_name is None, "The `view_name` must not be set."
        super().__init__(view_name=self.view_name, **kwargs)

    def get_url(self, obj, view_name, request, *args, **kwargs):
        return super().get_url(obj, self.view_name, request, *args, **kwargs) + "imports/"


class ImportFieldGetURLMixin:
    view_name = "imports-detail"

    def __init__(self, view_name=None, **kwargs):
        assert view_name is None, "The `view_name` must not be set."
        super().__init__(view_name=self.view_name, **kwargs)

    def get_url(self, obj, view_name, request, *args, **kwargs):
        imports_field = ImportsIdentityFromImporterField()
        importer_url = imports_field.get_url(obj.importer, None, request, *args, **kwargs)
        return f"{importer_url}{obj.pk}/"

    def use_pk_only_optimization(self):
        return False


class ImportIdentityField(ImportFieldGetURLMixin, IdentityField):
    pass


class ImportRelatedField(ImportFieldGetURLMixin, RelatedField):
    queryset = models.Import.objects.all()

    def get_object(self, view_name, view_args, view_kwargs):
        lookup_kwargs = {"importer__pk": view_kwargs["importer_pk"], "pk": view_kwargs["pk"]}
        return self.get_queryset().get(**lookup_kwargs)


class TaskGroupStatusCountField(serializers.IntegerField, serializers.ReadOnlyField):
    """Serializer field for counting the tasks on a task group in a given state."""

    def __init__(self, state, *args, **kwargs):
        self.state = state
        super().__init__(*args, **kwargs)

    def get_attribute(self, instance):
        return instance.tasks.filter(state=self.state).count()
