# Publish and Host

This section assumes that you have a repository with content in it (a repository version). To do
this, see the [sync](site:/pulp_file/docs/user/guides/01-sync/) or [upload](site:/pulp_file/docs/user/guides/02-upload/) documentation.

## Create a Publication (manually)

=== "Create Publication"

    ```bash
    #!/usr/bin/env bash
    echo "Create a new publication specifying the repository_version."
    PUBLICATION_HREF=$(pulp file publication create --repository $REPO_NAME --version 1 | jq -r '.pulp_href')

    echo "Inspecting Publication."
    pulp show --href $PUBLICATION_HREF
    ```

=== "Output"

    ```json
    {
        "pulp_created": "2019-05-16T19:28:42.971611Z",
        "pulp_href": "/pulp/api/v3/publications/file/file/7d5440f6-202c-4e71-ace2-14c534f6df9e/",
        "distributions": [],
        "publisher": null,
        "repository": "/pulp/api/v3/repositories/e242c556-bf46-4330-9c81-0be5432e55ba/file/file/",
        "repository_version": "/pulp/api/v3/repositories/e242c556-bf46-4330-9c81-0be5432e55ba/file/file/versions/1/"
    }
    ```

## Create a Distribution for the Publication

=== "Create Distribution"

    ```bash
    #!/usr/bin/env bash

    export DIST_NAME=$(head /dev/urandom | tr -dc a-z | head -c5)
    export DIST_BASE_PATH=$(head /dev/urandom | tr -dc a-z | head -c5)

    # Distributions are created asynchronously.
    echo "Creating distribution \
      (name=$DIST_NAME, base_path=$DIST_BASE_PATH publication=$PUBLICATION_HREF)."
    pulp file distribution create \
      --name $DIST_NAME \
      --base-path $DIST_BASE_PATH \
      --publication $PUBLICATION_HREF

    echo "Inspecting Distribution."
    pulp file distribution show --name $DIST_NAME
    ```

=== "Output"

    ```json
    {
        "pulp_created": "2019-05-16T19:28:45.135868Z",
        "pulp_href": "/pulp/api/v3/distributions/file/file/9e9e07cb-b30f-41c5-a98b-583185f907e2/",
        "base_path": "foo",
        "base_url": "localhost:24816/pulp/content/foo",
        "content_guard": null,
        "name": "baz",
        "repository": null,
        "publication": "/pulp/api/v3/publications/file/file/7d5440f6-202c-4e71-ace2-14c534f6df9e/"
    }
    ```

## Download `1.iso` from Pulp

=== "Download after `sync`"

    ```bash
    #!/usr/bin/env bash
    DISTRIBUTION_BASE_URL=$(pulp file distribution show --name $DIST_NAME | jq -r '.base_url')

    # Next we download a file from the distribution
    echo "Downloading file from Distribution via the content app."
    echo ${DISTRIBUTION_BASE_URL}1.iso
    http -d ${DISTRIBUTION_BASE_URL}1.iso
    ```

=== "Download after upload"

    ```bash
    #!/usr/bin/env bash
    DISTRIBUTION_BASE_URL=$(pulp file distribution show --name $DIST_NAME | jq -r '.base_url')

    echo "Downloading file from Distribution via the content app."
    echo $DISTRIBUTION_BASE_URL/$ARTIFACT_RELATIVE_PATH
    # This will default to http://
    http -d $DISTRIBUTION_BASE_URL/$ARTIFACT_RELATIVE_PATH
    ```

## Automate Publication and Distribution

With a little more initial setup, you can have publications and distributions for your repositories
updated automatically when new repository versions are created.

```bash
# This configures the repository to produce new publications when a new version is created
pulp file repository update --name $REPO_NAME --autopublish

# This configures the distribution to be track the latest repository version for a given repository
pulp file distribution update --name $DIST_NAME --repository $REPO_NAME
```
