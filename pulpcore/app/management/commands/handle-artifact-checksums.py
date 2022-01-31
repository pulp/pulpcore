import os

from gettext import gettext as _

from django.conf import settings
from django.core.management import BaseCommand, CommandError
from django.db.models import Q, Sum
from pulpcore import constants
from pulpcore.app import pulp_hashlib
from pulpcore.plugin.models import (
    Artifact,
    Content,
    ContentArtifact,
    RemoteArtifact,
    RepositoryVersion,
)

import logging

log = logging.getLogger("")

CHUNK_SIZE = 1024 * 1024  # 1 Mb


class Command(BaseCommand):
    """
    Django management command for populating or removing checksums on artifacts.
    """

    help = _("Handle missing and forbidden checksums on the artifacts")

    def add_arguments(self, parser):
        parser.add_argument("--report", action="store_true")
        parser.add_argument("--checksums", help=_("Comma separated list of checksums to evaluate"))

    def _print_out_repository_version_hrefs(self, repo_versions):
        """
        Print out repository version href from a query of repo versions.

        Args:
            repo_versions (django.db.models.QuerySet): repository versions query

        Returns None
        """
        for repo_version in repo_versions.iterator():
            self.stdout.write(
                _(
                    "/repositories/{plugin}/{type}/{pk}/versions/{number}/".format(
                        plugin=repo_version.repository.pulp_type.split(".")[0],
                        type=repo_version.repository.pulp_type.split(".")[1],
                        pk=str(repo_version.repository.pk),
                        number=repo_version.number,
                    )
                )
            )

    def _show_on_demand_content(self, checksums):
        query = Q(pk__in=[])
        for checksum in checksums:
            query |= Q(**{f"{checksum}__isnull": False})

        remote_artifacts = RemoteArtifact.objects.filter(query).filter(
            content_artifact__artifact__isnull=True
        )
        ras_size = remote_artifacts.aggregate(Sum("size"))["size__sum"]

        content_artifacts = ContentArtifact.objects.filter(remoteartifact__pk__in=remote_artifacts)
        content = Content.objects.filter(contentartifact__pk__in=content_artifacts)
        repo_versions = RepositoryVersion.objects.with_content(content).select_related("repository")

        self.stdout.write(
            _("Found {} on-demand content units with forbidden checksums.").format(content.count())
        )
        if content.count():
            self.stdout.write(
                _("There is approx {:.2f}Mb of content to be downloaded.").format(
                    ras_size / (1024**2)
                )
            )

        if repo_versions.exists():
            self.stdout.write(_("\nAffected repository versions with remote content:"))
            self._print_out_repository_version_hrefs(repo_versions)

    def _show_immediate_content(self, forbidden_checksums):
        allowed_checksums = set(
            constants.ALL_KNOWN_CONTENT_CHECKSUMS.symmetric_difference(forbidden_checksums)
        )
        query_forbidden = Q()
        query_required = Q()
        for checksum in forbidden_checksums:
            query_forbidden |= Q(**{f"{checksum}__isnull": False})

        for allowed_checksum in allowed_checksums:
            query_required |= Q(**{f"{allowed_checksum}__isnull": True})

        artifacts = Artifact.objects.filter(query_forbidden | query_required)
        content_artifacts = ContentArtifact.objects.filter(artifact__in=artifacts)
        content = Content.objects.filter(contentartifact__pk__in=content_artifacts)
        repo_versions = RepositoryVersion.objects.with_content(content).select_related("repository")

        self.stdout.write(
            _("Found {} downloaded content units with forbidden or missing checksums.").format(
                content.count()
            )
        )
        if content.count() > 0:
            self.stdout.write(
                _("There is approx. {:.2f}Mb content data to be re-hashed.").format(
                    artifacts.aggregate(Sum("size"))["size__sum"] / (1024**2)
                )
            )

        if repo_versions.exists():
            self.stdout.write(_("\nAffected repository versions with present content:"))
            self._print_out_repository_version_hrefs(repo_versions)

    def _download_artifact(self, artifact, checksum, file_path):
        restored = False
        for ca in artifact.content_memberships.all():
            if not restored:
                for ra in ca.remoteartifact_set.all():
                    remote = ra.remote.cast()
                    if remote.policy == "immediate":
                        self.stdout.write(_("Restoring missing file {}").format(file_path))
                        downloader = remote.get_downloader(ra)
                        dl_result = downloader.fetch()
                        # FIXME in case url is not available anymore this will break
                        if dl_result.artifact_attributes["sha256"] == artifact.sha256:
                            with open(dl_result.path, "rb") as src:
                                filename = artifact.file.name
                                artifact.file.save(filename, src, save=False)
                            setattr(artifact, checksum, dl_result.artifact_attributes[checksum])
                            restored = True
                            break
            else:
                break
        return restored

    def _report(self, allowed_checksums):
        if allowed_checksums:
            allowed_checksums = allowed_checksums.split(",")
            if "sha256" not in allowed_checksums:
                raise CommandError(_("Checksums must contain sha256"))
        else:
            allowed_checksums = settings.ALLOWED_CONTENT_CHECKSUMS

        forbidden_checksums = set(constants.ALL_KNOWN_CONTENT_CHECKSUMS).difference(
            allowed_checksums
        )

        self.stderr.write(
            _(
                "Warning: the handle-artifact-checksums report is in "
                "tech preview and may change in the future."
            )
        )
        self._show_on_demand_content(forbidden_checksums)
        self._show_immediate_content(forbidden_checksums)

    def handle(self, *args, **options):

        if options["report"]:
            self._report(options["checksums"])
            return

        if options["checksums"] and not options["report"]:
            self.stdout.write(_("Checksums cannot be supplied without --report argument"))
            exit(1)

        log.setLevel(logging.ERROR)
        hrefs = set()
        for checksum in settings.ALLOWED_CONTENT_CHECKSUMS:
            params = {f"{checksum}__isnull": True}
            artifacts_qs = Artifact.objects.filter(**params)
            artifacts = []
            for a in artifacts_qs.iterator():
                hasher = pulp_hashlib.new(checksum)
                try:
                    with a.file as fp:
                        for chunk in fp.chunks(CHUNK_SIZE):
                            hasher.update(chunk)
                    setattr(a, checksum, hasher.hexdigest())
                except FileNotFoundError:
                    file_path = os.path.join(settings.MEDIA_ROOT, a.file.name)
                    restored = self._download_artifact(a, checksum, file_path)
                    if not restored:
                        hrefs.add(file_path)
                artifacts.append(a)

                if len(artifacts) >= 1000:
                    Artifact.objects.bulk_update(objs=artifacts, fields=[checksum], batch_size=1000)
                    artifacts.clear()

            if artifacts:
                Artifact.objects.bulk_update(objs=artifacts, fields=[checksum])

        if hrefs:
            raise CommandError(
                _("Some files that were missing could not be restored: {}").format(hrefs)
            )

        forbidden_checksums = set(constants.ALL_KNOWN_CONTENT_CHECKSUMS).difference(
            settings.ALLOWED_CONTENT_CHECKSUMS
        )
        for checksum in forbidden_checksums:
            search_params = {f"{checksum}__isnull": False}
            update_params = {f"{checksum}": None}
            artifacts_qs = Artifact.objects.filter(**search_params)
            if artifacts_qs.exists():
                self.stdout.write(
                    _("Removing forbidden checksum {} from database").format(checksum)
                )
                artifacts_qs.update(**update_params)

        self.stdout.write(_("Finished aligning checksums with settings.ALLOWED_CONTENT_CHECKSUMS"))
