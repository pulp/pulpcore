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

@exporters_api = PulpcoreClient::ExportersPulpApi.new
@exports_api = PulpcoreClient::ExportersPulpExportsApi.new
@filerepositories_api = PulpFileClient::RepositoriesFileApi.new
@repoversions_api = PulpFileClient::RepositoriesFileVersionsApi.new
@fileremotes_api = PulpFileClient::RemotesFileApi.new
@tasks_api = PulpcoreClient::TasksApi.new




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

# Create a File Remote
remote_url = 'https://fixtures.pulpproject.org/file/PULP_MANIFEST'
remote_data = PulpFileClient::FileFileRemote.new({name: 'bar48', url: remote_url})
file_remote = @fileremotes_api.create(remote_data)

# Create a Repository
repository_data = PulpFileClient::FileFileRepository.new({name: 'foo48'})
file_repository = @filerepositories_api.create(repository_data)

# Sync a Repository
repository_sync_data = PulpFileClient::RepositorySyncURL.new({remote: file_remote.pulp_href})
sync_response = @filerepositories_api.sync(file_repository.pulp_href, repository_sync_data)

# Monitor the sync task
created_resources = monitor_task(sync_response.task)

repository_version_1 = @repoversions_api.read(created_resources[0])

# Create an exporter
exporter = @exporters_api.create({name: 'foo48', path: '/tmp/foo', repositories:[file_repository.pulp_href]})

# Create an export
export_response = @exports_api.create(exporter.pulp_href, versions: [repository_version_1.pulp_href])
created_resources = monitor_task(export_response.task)

# List exports
exports = @exports_api.list(exporter.pulp_href)

exit
