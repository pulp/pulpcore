import asyncio
import tempfile

from .api import create_pipeline, EndStage
from .artifact_stages import (
    ACSArtifactHandler,
    ArtifactDownloader,
    ArtifactSaver,
    QueryExistingArtifacts,
    RemoteArtifactSaver,
)
from .content_stages import (
    ContentAssociation,
    ContentSaver,
    QueryExistingContents,
    ResolveContentFutures,
)


class DeclarativeVersion:
    def __init__(self, first_stage, repository, mirror=False, acs=False):
        """
        A pipeline that creates a new [pulpcore.plugin.models.RepositoryVersion][] from a
        stream of [pulpcore.plugin.stages.DeclarativeContent][] objects.

        The plugin writer needs to specify a first_stage that will create a
        [pulpcore.plugin.stages.DeclarativeContent][] object for each Content unit that should
        exist in the [pulpcore.plugin.models.RepositoryVersion][].

        The pipeline stages perform the following steps by default:

        1. Create the new [pulpcore.plugin.models.RepositoryVersion][]
        2. Use the provided `first_stage` to construct
           [pulpcore.plugin.stages.DeclarativeContent][]
        3. Query existing artifacts to determine which are already local to Pulp with
           [pulpcore.plugin.stages.QueryExistingArtifacts][]
        4. Download any undownloaded [pulpcore.plugin.models.Artifact][] objects with
           [pulpcore.plugin.stages.ArtifactDownloader][]
        5. Save the newly downloaded [pulpcore.plugin.models.Artifact][] objects with
           [pulpcore.plugin.stages.ArtifactSaver][]
        6. Query for Content units already present in Pulp with
           [pulpcore.plugin.stages.QueryExistingContents][]
        7. Save new Content units not yet present in Pulp with
           [pulpcore.plugin.stages.ContentSaver][]
        8. Attach [pulpcore.plugin.models.RemoteArtifact][] to the
           [pulpcore.plugin.models.Content][] via
           [pulpcore.plugin.stages.RemoteArtifactSaver][]
        9. Resolve the attached [asyncio.Future][] of
           [pulpcore.plugin.stages.DeclarativeContent][] with
           [pulpcore.plugin.stages.ResolveContentFutures][]
        10. Associate all content units with the new
            [pulpcore.plugin.models.RepositoryVersion][] with
            [pulpcore.plugin.stages.ContentAssociation][]
        11. Unassociate any content units not declared in the stream (only when mirror=True)
            with [pulpcore.plugin.stages.ContentUnassociation][]

        To do this, the plugin writer should subclass the
        [pulpcore.plugin.stages.Stage][] class and define its
        :meth:`run()` interface which returns a coroutine. This coroutine should
        download metadata, create the corresponding
        [pulpcore.plugin.stages.DeclarativeContent][] objects, and put them into the
        [asyncio.Queue][] via :meth:`put()` to send them down the pipeline. For example::

            class MyFirstStage(Stage):

                def __init__(remote):
                    self.remote = remote

                async def run(self):
                    downloader = remote.get_downloader(url=remote.url)
                    result = await downloader.run()
                    for entry in read_my_metadata_file_somehow(result.path)
                        unit = MyContent(entry)  # make the content unit in memory-only
                        artifact = Artifact(entry)  # make Artifact in memory-only
                        da = DeclarativeArtifact(artifact, url, entry.relative_path, self.remote)
                        dc = DeclarativeContent(content=unit, d_artifacts=[da])
                        await self.put(dc)

        To use your first stage with the pipeline you have to instantiate the subclass and pass it
        to [pulpcore.plugin.stages.DeclarativeVersion][].

        1. Create the instance of the subclassed [pulpcore.plugin.stages.Stage][] object.
        2. Create the [pulpcore.plugin.stages.DeclarativeVersion][] instance, passing the
           [pulpcore.plugin.stages.Stage][] subclass instance to it
        3. Call the :meth:`~pulpcore.plugin.stages.DeclarativeVersion.create` method on your
           [pulpcore.plugin.stages.DeclarativeVersion][] instance

        Here is an example::

            first_stage = MyFirstStage(remote)
            DeclarativeVersion(first_stage, repository_version).create()

        Args:
            first_stage (pulpcore.plugin.stages.Stage) The first stage to receive
                [pulpcore.plugin.stages.DeclarativeContent][] from.
            repository (pulpcore.plugin.models.Repository) The repository receiving the
                new version.
            mirror (bool): 'True' removes content units from the
                [pulpcore.plugin.models.RepositoryVersion][] that are not
                requested in the [pulpcore.plugin.stages.DeclarativeVersion][] stream.
                'False' (additive) only adds content units observed in the
                :class:`~pulpcore.plugin.stages.DeclarativeVersion stream`, and does not remove any
                pre-existing units in the [pulpcore.plugin.models.RepositoryVersion][].
                'False' is the default.
            acs (bool): When set to 'True' a new stage is added to look for
                Alternate Content Sources.

        """
        self.first_stage = first_stage
        self.repository = repository
        self.mirror = mirror
        self.acs = acs

    def pipeline_stages(self, new_version):
        """
        Build the list of pipeline stages feeding into the ContentAssociation stage.

        Plugin-writers may override this method to build a custom pipeline. This
        can be achieved by returning a list with different stages or by extending
        the list returned by this method.

        Args:
            new_version (pulpcore.plugin.models.RepositoryVersion) The
                new repository version that is going to be built.

        Returns:
            list: List of [pulpcore.plugin.stages.Stage][] instances

        """
        pipeline = [
            self.first_stage,
            QueryExistingArtifacts(),
        ]
        if self.acs:
            pipeline.append(ACSArtifactHandler())
        pipeline.extend(
            [
                ArtifactDownloader(),
                ArtifactSaver(),
                QueryExistingContents(),
                ContentSaver(),
                RemoteArtifactSaver(),
                ResolveContentFutures(),
            ]
        )
        return pipeline

    def create(self):
        """
        Perform the work. This is the long-blocking call where all syncing occurs.

        Returns: The created RepositoryVersion or None if it represents no change from the latest.
        """
        with tempfile.TemporaryDirectory(dir="."):
            with self.repository.new_version() as new_version:
                loop = asyncio.get_event_loop()
                stages = self.pipeline_stages(new_version)
                stages.append(ContentAssociation(new_version, self.mirror))
                stages.append(EndStage())
                pipeline = create_pipeline(stages)
                loop.run_until_complete(pipeline)

        return new_version if new_version.complete else None
