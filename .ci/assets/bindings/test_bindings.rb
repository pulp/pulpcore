require 'pulpcore_client'
require 'pulp_file_client'
require 'tempfile'
require 'digest'


PulpcoreClient.configure do |config|
  config.host= "http://pulp:80"
  config.username= 'admin'
  config.password= 'password'
  config.debugging=true
end

PulpFileClient.configure do |config|
  config.host= "http://pulp:80"
  config.username= 'admin'
  config.password= 'password'
  config.debugging=true
end


@artifacts_api = PulpcoreClient::ArtifactsApi.new
@filerepositories_api = PulpFileClient::RepositoriesFileApi.new
@repoversions_api = PulpFileClient::RepositoriesFileVersionsApi.new
@filecontent_api = PulpFileClient::ContentFilesApi.new
@filedistributions_api = PulpFileClient::DistributionsFileApi.new
@filepublications_api = PulpFileClient::PublicationsFileApi.new
@fileremotes_api = PulpFileClient::RemotesFileApi.new
@tasks_api = PulpcoreClient::TasksApi.new
@uploads_api = PulpcoreClient::UploadsApi.new


def monitor_task(task_href)
    # Polls the Task API until the task is in a completed state.
    #
    # Prints the task details and a success or failure message. Exits on failure.
    #
    # Args:
    #    task_href(str): The href of the task to monitor
    #
    # Returns:
    #     list[str]: List of hrefs that identify resource created by the task
    completed = []
    task = @tasks_api.read(task_href)
    until ["completed", "failed", "canceled"].include? task.state
      sleep(2)
      task = @tasks_api.read(task_href)
    end
    if task.state == 'completed'
      task.created_resources
    else
      print("Task failed. Exiting.\n")
      exit(2)
    end
end

def content_range(start, finish, total)
  finish = finish > total ? total : finish
  "bytes #{start}-#{finish}/#{total}"
end

def upload_file_in_chunks(file_path)
    # Uploads a file using the Uploads API
    #
    # The file located at 'file_path' is uploaded in chunks of 200kb.
    #
    # Args:
    #     file_path (str): path to the file being uploaded to Pulp
    #
    # Returns:
    #     upload object
    response = ""
    File.open(file_path, "rb") do |file|
      total_size = File.size(file)
      upload_data = PulpcoreClient::Upload.new({size: total_size})
      response = @uploads_api.create(upload_data)
      upload_href = response.pulp_href
      chunksize = 200000
      offset = 0
      sha256 = Digest::SHA256.new
      until file.eof?
        chunk = file.read(chunksize)
        sha256.update(chunk)
        begin
          filechunk = Tempfile.new('fred')
          filechunk.write(chunk)
          filechunk.flush()
          actual_chunk_size = File.size(filechunk)
          response = @uploads_api.update(content_range(offset, offset + actual_chunk_size -1, total_size), upload_href, filechunk)
          offset += actual_chunk_size -1
        ensure
          filechunk.close
          filechunk.unlink
        end
      end
      upload_commit_response = @uploads_api.commit(upload_href, {sha256: sha256.hexdigest})
      created_resources = monitor_task(upload_commit_response.task)
      @artifacts_api.read(created_resources[0])
    end
end


artifact = upload_file_in_chunks(File.join(ENV['GITHUB_WORKSPACE'], 'template_config.yml'))

# Create a File Remote
remote_url = 'https://fixtures.pulpproject.org/file/PULP_MANIFEST'
remote_data = PulpFileClient::FileFileRemote.new({name: 'bar38', url: remote_url})
file_remote = @fileremotes_api.create(remote_data)

# Create a Repository
repository_data = PulpFileClient::FileFileRepository.new({name: 'foo38'})
file_repository = @filerepositories_api.create(repository_data)

# Sync a Repository
repository_sync_data = PulpFileClient::RepositorySyncURL.new({remote: file_remote.pulp_href})
sync_response = @filerepositories_api.sync(file_repository.pulp_href, repository_sync_data)

# Monitor the sync task
created_resources = monitor_task(sync_response.task)

repository_version_1 = @repoversions_api.read(created_resources[0])

# Create an artifact from a local file
file_path = File.join(ENV['GITHUB_WORKSPACE'], '.ci/assets/bindings/test_bindings.rb')
artifact = @artifacts_api.create(File.new(file_path))

# Create a FileContent from the artifact
filecontent_response = @filecontent_api.create('foo.tar.gz', {artifact: artifact.pulp_href})

created_resources = monitor_task(filecontent_response.task)

# Add the new FileContent to a repository version
repo_version_data = {add_content_units: [created_resources[0]]}
repo_version_response = @filerepositories_api.modify(file_repository.pulp_href, repo_version_data)

# Monitor the repo version creation task
created_resources = monitor_task(repo_version_response.task)

repository_version_2 = @repoversions_api.read(created_resources[0])

# List all the repository versions
@repoversions_api.list(file_repository.pulp_href)

# Create a publication from the latest version of the repository
publish_data = PulpFileClient::FileFilePublication.new({repository: file_repository.pulp_href})
publish_response = @filepublications_api.create(publish_data)

# Monitor the publish task
created_resources = monitor_task(publish_response.task)
publication_href = created_resources[0]

distribution_data = PulpFileClient::FileFileDistribution.new({name: 'baz38', base_path: 'foo38', publication: publication_href})
distribution = @filedistributions_api.create(distribution_data)
