require 'pulpcore_client'
require 'pulp_file_client'
require 'tempfile'
require 'digest'


PulpcoreClient.configure do |config|
  config.host= "http://localhost:24817"
  config.username= 'admin'
  config.password= 'password'
  config.debugging=true
end

PulpFileClient.configure do |config|
  config.host= "http://localhost:24817"
  config.username= 'admin'
  config.password= 'password'
  config.debugging=true
end


@artifacts_api = PulpcoreClient::ArtifactsApi.new
@repositories_api = PulpcoreClient::RepositoriesApi.new
@repoversions_api = PulpcoreClient::RepositoriesVersionsApi.new
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
      upload_href = response._href
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
          response = @uploads_api.update(upload_href, content_range(offset, offset + actual_chunk_size -1, total_size), filechunk)
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


artifact = upload_file_in_chunks(File.join(ENV['TRAVIS_BUILD_DIR'], '.travis.yml'))

# Create a File Remote
remote_url = 'https://repos.fedorapeople.org/pulp/pulp/demo_repos/test_file_repo/PULP_MANIFEST'
remote_data = PulpFileClient::FileRemote.new({name: 'bar38', url: remote_url})
file_remote = @fileremotes_api.create(remote_data)

# Create a Repository
repository_data = PulpcoreClient::Repository.new({name: 'foo38'})
repository = @repositories_api.create(repository_data)

# Sync a Repository
repository_sync_data = PulpFileClient::RepositorySyncURL.new({repository: repository._href})
sync_response = @fileremotes_api.sync(file_remote._href, repository_sync_data)

# Monitor the sync task
created_resources = monitor_task(sync_response.task)

repository_version_1 = @repoversions_api.read(created_resources[0])

# Create an artifact from a local file
file_path = File.join(ENV['TRAVIS_BUILD_DIR'], '.travis/test_bindings.rb')
artifact = @artifacts_api.create({file: File.new(file_path)})

# Create a FileContent from the artifact
file_data = PulpFileClient::FileContent.new({relative_path: 'foo.tar.gz', _artifact: artifact._href})
filecontent = @filecontent_api.create(file_data)

# Add the new FileContent to a repository version
repo_version_data = {add_content_units: [filecontent._href]}
repo_version_response = @repoversions_api.create(repository._href, repo_version_data)

# Monitor the repo version creation task
created_resources = monitor_task(repo_version_response.task)

repository_version_2 = @repoversions_api.read(created_resources[0])

# Create a publication from the latest version of the repository
publish_data = PulpFileClient::FilePublication.new({repository: repository._href})
publish_response = @filepublications_api.create(publish_data)

# Monitor the publish task
created_resources = monitor_task(publish_response.task)
publication_href = created_resources[0]

distribution_data = PulpFileClient::FileDistribution.new({name: 'baz38', base_path: 'foo38', publication: publication_href})
distribution = @filedistributions_api.create(distribution_data)
