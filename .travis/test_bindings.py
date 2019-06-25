from pulpcore.client.pulpcore import (ApiClient as CoreApiClient, ArtifactsApi, Configuration,
                                      Repository, RepositoriesApi, RepositoriesVersionsApi,
                                      TasksApi, UploadsApi)
from pulpcore.client.pulp_file import (ApiClient as FileApiClient, ContentFilesApi,
                                       FileContent, DistributionsFileApi,
                                       FileDistribution, PublicationsFileApi,
                                       RemotesFileApi, FileRemote, RepositorySyncURL,
                                       FilePublication)
from pprint import pprint
from time import sleep
import hashlib
import os
import requests
from tempfile import NamedTemporaryFile


def monitor_task(task_href):
    """Polls the Task API until the task is in a completed state.

    Prints the task details and a success or failure message. Exits on failure.

    Args:
        task_href(str): The href of the task to monitor

    Returns:
        list[str]: List of hrefs that identify resource created by the task

    """
    completed = ['completed', 'failed', 'canceled']
    task = tasks.read(task_href)
    while task.state not in completed:
        sleep(2)
        task = tasks.read(task_href)
    pprint(task)
    if task.state == 'completed':
        print("The task was successfful.")
        return task.created_resources
    else:
        print("The task did not finish successfully.")
        exit()


def upload_file_in_chunks(file_path):
    """Uploads a file using the Uploads API

    The file located at 'file_path' is uploaded in chunks of 200kb.

    Args:
        file_path (str): path to the file being uploaded to Pulp

    Returns:
        upload object
    """
    with open(file_path, 'rb') as full_file:
        size = os.stat(file_path).st_size
        chunk_size = 200000
        offset = 0
        md5hasher = hashlib.new('md5')
        while True:
            chunk = full_file.read(chunk_size)
            if not chunk:
                break
            actual_chunk_size = len(chunk)
            content_range = 'bytes {start}-{end}/{size}'.format(start=offset,
                                                                end=offset+actual_chunk_size-1,
                                                                size=size)
            with NamedTemporaryFile() as file_chunk:
                file_chunk.write(chunk)
                if not offset:
                    upload = uploads.start_upload(file=file_chunk.name, content_range=content_range)
                else:
                    upload = uploads.continue_upload(upload_href=upload.href,
                                                     file=file_chunk.name,
                                                     content_range=content_range)
            offset += chunk_size
            md5hasher.update(chunk)
        uploads.finish_upload(upload_href=upload.href, md5=md5hasher.hexdigest())
    return upload


# Configure HTTP basic authorization: basic
configuration = Configuration()
configuration.username = 'admin'
configuration.password = 'admin'
configuration.safe_chars_for_path_param = '/'

core_client = CoreApiClient(configuration)
file_client = FileApiClient(configuration)

# Create api clients for all resource types
artifacts = ArtifactsApi(core_client)
repositories = RepositoriesApi(core_client)
repoversions = RepositoriesVersionsApi(core_client)
filecontent = ContentFilesApi(file_client)
filedistributions = DistributionsFileApi(core_client)
filepublications = PublicationsFileApi(file_client)
fileremotes = RemotesFileApi(file_client)
tasks = TasksApi(core_client)
uploads = UploadsApi(core_client)


# Test creating an Artifact from a 1mb file uploaded in 200kb chunks
with NamedTemporaryFile() as downloaded_file:
    response = requests.get(
        'https://repos.fedorapeople.org/repos/pulp/pulp/demo_repos/test_bandwidth_repo/'
        'pulp-large_1mb_test-packageA-0.1.1-1.fc14.noarch.rpm')
    response.raise_for_status()
    downloaded_file.write(response.content)
    upload = upload_file_in_chunks(downloaded_file.name)
    pprint(upload)
    artifact = artifacts.create(upload=upload.href)
    pprint(artifact)

# Create a File Remote
remote_url = 'https://repos.fedorapeople.org/pulp/pulp/demo_repos/test_file_repo/PULP_MANIFEST'
remote_data = FileRemote(name='bar25', url=remote_url)
file_remote = fileremotes.create(remote_data)
pprint(file_remote)

# Create a Repository
repository_data = Repository(name='foo25')
repository = repositories.create(repository_data)
pprint(repository)

# Sync a Repository
repository_sync_data = RepositorySyncURL(repository=repository.href)
sync_response = fileremotes.sync(file_remote.href, repository_sync_data)

pprint(sync_response)

# Monitor the sync task
created_resources = monitor_task(sync_response.task)

repository_version_1 = repoversions.read(created_resources[0])
pprint(repository_version_1)

# Create an artifact from a local file
artifact = artifacts.create(file='test_bindings.py')
pprint(artifact)

# Create a FileContent from the artifact
file_data = FileContent(relative_path='foo.tar.gz', artifact=artifact.href)
filecontent = filecontent.create(file_data)
pprint(filecontent)

# Add the new FileContent to a repository version
repo_version_data = {'add_content_units': [filecontent.href]}
repo_version_response = repoversions.create(repository.href, repo_version_data)

# Monitor the repo version creation task
created_resources = monitor_task(repo_version_response.task)

repository_version_2 = repoversions.read(created_resources[0])
pprint(repository_version_2)

# Create a publication from the latest version of the repository
publish_data = FilePublication(repository=repository.href)
publish_response = filepublications.create(publish_data)

# Monitor the publish task
created_resources = monitor_task(publish_response.task)
publication_href = created_resources[0]

distribution_data = FileDistribution(name='baz25', base_path='foo25', publication=publication_href)
distribution = filedistributions.create(distribution_data)
pprint(distribution)
