# Synchronize a git repository

`pulp_file` can sync the files from a `git` repository with a `FileGitRemote`.

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

## Create a new git remote `bar`

=== "Create Remote bar"

    ```bash
    #!/usr/bin/env bash
    export REMOTE_NAME=$(head /dev/urandom | tr -dc a-z | head -c5)
    echo "Creating a remote that points to an external git repository"
    pulp file remote --type git create --name $REMOTE_NAME \
        --url 'https://github.com/pulp/pulpcore.git'
    
    echo "Inspecting new Remote."
    pulp file remote -t git show --name $REMOTE_NAME
    ```

=== "Output"

    ```json
    {
        "name": "bar",
        "prn": "prn:file.filegitremote:019c2fd7-c89e-7ae7-81ee-92ef2f0dae85",
        "proxy_url": null,
        "pulp_created": "2026-02-05T22:06:36.702964Z",
        "pulp_href": "/pulp/api/v3/remotes/file/git/019c2fd7-c89e-7ae7-81ee-92ef2f0dae85/",
        "pulp_labels": {},
        "pulp_last_updated": "2026-02-05T22:06:36.702974Z",
        "tls_validation": true,
        "url": "https://github.com/pulp/pulpcore.git",
        "git_ref": "HEAD"
    }
    ```

## Sync repository `foo` using git remote `bar`

=== "Sync foo using bar"

    ```bash
    #!/usr/bin/env bash
    echo "Syncing the repository using the remote."
    pulp file repository sync --name $REPO_NAME --remote file:git:$REMOTE_NAME
    
    echo "Inspecting RepositoryVersion."
    pulp file repository version show --repository $REPO_NAME --version 1
    ```

=== "Output"

    ```json
    {
        "pulp_href": "/pulp/api/v3/repositories/file/file/019c2fda-4690-774e-a374-dedab9f2e64a/versions/1/",
        "prn": "prn:core.repositoryversion:019c2fda-81e9-7161-914b-8fdeba1b31ac",
        "pulp_created": "2026-02-05T22:09:35.211703Z",
        "pulp_last_updated": "2026-02-05T22:09:48.661887Z",
        "number": 1,
        "repository": "/pulp/api/v3/repositories/file/file/019c2fda-4690-774e-a374-dedab9f2e64a/",
        "base_version": null,
        "content_summary": {
            "added": {
            "file.file": {
                "count": 695,
                "href": "/pulp/api/v3/content/file/files/?repository_version_added=/pulp/api/v3/repositories/file/file/019c2fda-4690-774e-a374-dedab9f2e64a/versions/1/"
            }
            },
            "removed": {},
            "present": {
            "file.file": {
                "count": 695,
                "href": "/pulp/api/v3/content/file/files/?repository_version=/pulp/api/v3/repositories/file/file/019c2fda-4690-774e-a374-dedab9f2e64a/versions/1/"
            }
            }
        },
        "vuln_report": "/pulp/api/v3/vuln_report/?repo_versions=prn:core.repositoryversion:019c2fda-81e9-7161-914b-8fdeba1b31ac"
    }
    ```

## Specify a git ref to sync from

=== "Create Remote bar"

    ```bash
    #!/usr/bin/env bash
    echo "Update git remote to new git_ref"
    pulp file remote -t git update --name $REMOTE_NAME --git-ref "3.102.0"
    ```

=== "Output"

    ```json
    {
        "name": "bar",
        "prn": "prn:file.filegitremote:019c2fd7-c89e-7ae7-81ee-92ef2f0dae85",
        "proxy_url": null,
        "pulp_created": "2026-02-05T22:06:36.702964Z",
        "pulp_href": "/pulp/api/v3/remotes/file/git/019c2fd7-c89e-7ae7-81ee-92ef2f0dae85/",
        "pulp_labels": {},
        "pulp_last_updated": "2026-02-05T22:06:36.702974Z",
        "tls_validation": true,
        "url": "https://github.com/pulp/pulpcore.git",
        "git_ref": "3.102.0"
    }
