# Synchronize a Repository

In this section, there is provided a basic workflow for synchronizing a remote repository.

## Create a repository `foo`

=== "Create Repository foo"

    ```bash
    #!/usr/bin/env bash
    export REPO_NAME=$(head /dev/urandom | tr -dc a-z | head -c5)
    
    echo "Creating a new repository named $REPO_NAME."
    pulp file repository create --name $REPO_NAME
    
    echo "Inspecting repository."
    pulp file repository show --name $REPO_NAME
    ```

=== "Output"

    ```json
    {
        "pulp_created": "2019-05-16T19:23:55.224096Z",
        "pulp_href": "/pulp/api/v3/repositories/file/file/680f18e7-0513-461f-b067-436b03285e4c/",
        "latest_version_href": null,
        "versions_href": "/pulp/api/v3/repositories/file/file/680f18e7-0513-461f-b067-436b03285e4c/versions/",
        "description": "",
        "name": "foo"
    }
    ```

## Create a new remote `bar`

=== "Create Remote bar"

    ```bash
    #!/usr/bin/env bash
    export REMOTE_NAME=$(head /dev/urandom | tr -dc a-z | head -c5)
    echo "Creating a remote that points to an external source of files."
    pulp file remote create --name $REMOTE_NAME \
        --url 'https://fixtures.pulpproject.org/file/PULP_MANIFEST'
    
    echo "Inspecting new Remote."
    pulp file remote show --name $REMOTE_NAME
    ```

=== "Output"

    ```json
    {
        "pulp_created": "2019-05-16T19:23:56.771326Z",
        "pulp_href": "/pulp/api/v3/remotes/file/file/e682efef-3974-4366-aece-a333bfaec9f3/",
        "pulp_last_updated": "2019-05-16T19:23:56.771341Z",
        "download_concurrency": 20,
        "name": "bar",
        "policy": "immediate",
        "proxy_url": "",
        "ssl_ca_certificate": null,
        "ssl_client_certificate": null,
        "ssl_client_key": null,
        "ssl_validation": true,
        "url": "https://fixtures.pulpproject.org/file/PULP_MANIFEST",
        "validate": true
    }
    ```

## Sync repository `foo` using remote `bar`

=== "Sync foo using bar"

    ```bash
    #!/usr/bin/env bash
    echo "Syncing the repository using the remote."
    pulp file repository sync --name $REPO_NAME --remote $REMOTE_NAME
    
    echo "Inspecting RepositoryVersion."
    pulp file repository version show --repository $REPO_NAME --version 1
    ```

=== "Output"

    ```json
    {
        "pulp_created": "2019-05-16T19:23:58.230896Z",
        "pulp_href": "/pulp/api/v3/repositories/file/file/680f18e7-0513-461f-b067-436b03285e4c/versions/1/",
        "base_version": null,
        "content_summary": {
            "added": {
                "file.file": {
                    "count": 3,
                    "href": "/pulp/api/v3/content/file/files/?repository_version_added=/pulp/api/v3/repositories/file/file/680f18e7-0513-461f-b067-436b03285e4c/versions/1/"
                }
            },
            "present": {
                "file.file": {
                    "count": 3,
                    "href": "/pulp/api/v3/content/file/files/?repository_version=/pulp/api/v3/repositories/file/file/680f18e7-0513-461f-b067-436b03285e4c/versions/1/"
                }
            },
            "removed": {}
        },
        "number": 1
    }
    ```
