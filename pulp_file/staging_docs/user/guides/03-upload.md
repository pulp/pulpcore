# Upload Content

The section shows how to upload content to Pulp. 

## Create a Repository `foo`

=== "Create Repository"

    ```bash
    pulp file repository create \
      --name foo \
      --autopublish
    ```

=== "Output"

    ```json
    {
      "pulp_href": "/pulp/api/v3/repositories/file/file/018db957-1997-78b9-a2db-7754434bdf12/",
      "pulp_created": "2024-02-17T23:11:49.656603Z",
      "versions_href": "/pulp/api/v3/repositories/file/file/018db957-1997-78b9-a2db-7754434bdf12/versions/",
      "pulp_labels": {},
      "latest_version_href": "/pulp/api/v3/repositories/file/file/018db957-1997-78b9-a2db-7754434bdf12/versions/0/",
      "name": "foo",
      "description": null,
      "retain_repo_versions": null,
      "remote": null,
      "autopublish": true,
      "manifest": "PULP_MANIFEST"
    }
    ```

## Upload a file into `foo`

=== "Upload file"

    ```bash
    pulp file content upload \
      --repository foo \
      --file ./testfile.txt \
      --relative-path testfile.txt
    ```

=== "Output"

    ```bash
    Started background task /pulp/api/v3/tasks/018db958-a002-7e7d-89a7-f30b0d4eb436/
    .Done.
    {
      "pulp_href": "/pulp/api/v3/repositories/file/file/018db957-1997-78b9-a2db-7754434bdf12/versions/1/",
      "pulp_created": "2024-02-17T23:13:29.787710Z",
      "number": 1,
      "repository": "/pulp/api/v3/repositories/file/file/018db957-1997-78b9-a2db-7754434bdf12/",
      "base_version": null,
      "content_summary": {
        "added": {
          "file.file": {
            "count": 1,
            "href": "/pulp/api/v3/content/file/files/?repository_version_added=/pulp/api/v3/repositories/file/file/018db957-1997-78b9-a2db-7754434bdf12/versions/1/"
          }
        },
        "removed": {},
        "present": {
          "file.file": {
            "count": 1,
            "href": "/pulp/api/v3/content/file/files/?repository_version=/pulp/api/v3/repositories/file/file/018db957-1997-78b9-a2db-7754434bdf12/versions/1/"
          }
        }
      }
    }
    ```

## Create a Distribution for 'foo'

=== "Create Distribution"

    ```bash
    pulp file distribution create \
      --name foo_latest \
      --repository file:file:foo \
      --base-path file/foo
    ```

=== "Output"

    ```bash
    Started background task /pulp/api/v3/tasks/018db95a-5685-73bb-92f0-b2549483888a/
    Done.
    {
      "pulp_href": "/pulp/api/v3/distributions/file/file/018db95a-57a6-7f31-9d53-43f277664407/",
      "pulp_created": "2024-02-17T23:15:22.151052Z",
      "base_path": "file/foo",
      "base_url": "http://localhost:5001/pulp/content/file/foo/",
      "content_guard": null,
      "hidden": false,
      "pulp_labels": {},
      "name": "foo_latest",
      "repository": "/pulp/api/v3/repositories/file/file/018db957-1997-78b9-a2db-7754434bdf12/",
      "publication": null
    }
    ```

## Check Distribution

=== "Get "

    ```bash
    http http://localhost:5001/pulp/content/file/foo/
    ```

=== "Output"

    ```sh
    HTTP/1.1 200 OK
    Connection: keep-alive
    Content-Length: 501
    Content-Type: text/html
    Date: Sat, 17 Feb 2024 23:17:45 GMT
    Server: nginx/1.22.1
    
    <html>
    <head><title>Index of /pulp/content/file/foo/</title></head>
    <body bgcolor="white">
    <h1>Index of /pulp/content/file/foo/</h1>
    <hr><pre><a href="../">../</a>
    <a href="PULP_MANIFEST">PULP_MANIFEST</a>                                                                                       17-Feb-2024 23:13  81 Bytes
    <a href="testfile.txt">testfile.txt</a>                                                                                        17-Feb-2024 23:13  25 Bytes
    </pre><hr></body>
    </html>
    ```
