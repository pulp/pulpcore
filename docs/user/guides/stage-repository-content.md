# Manage Repository Staging

A repository staging area holds content associated with a repository before it belongs to a repository version.

Staged content is not served by a distribution and does not trigger checks and operations that creating a repository version would.
Because it doesn't have those checks, it can be used to avoid repository version creation overhead.

You can inspect the staging area, commit its content into a new repository version, or discard it.

These examples use the file plugin, but staging works with repositories from any plugin.
Replace `/repositories/file/file/` with your plugin's repository endpoint.

The commands use HTTPie and the `admin` user.
Set `PULP_API_URL` to the API base URL, including its port and version, without a trailing slash.
Set `PULP_PASSWORD` to the `admin` password and `REPOSITORY_NAME` to the name of the new repository.

## Enable Staging

Set `staging_enabled` when creating a repository.
It defaults to `false`.

```bash
http --auth "admin:$PULP_PASSWORD" POST "$PULP_API_URL/repositories/file/file/" \
  name="$REPOSITORY_NAME" staging_enabled:=true
```

The staging endpoints return `404` while staging is disabled for the repository.
Set `REPOSITORY_ID` to the ID in the returned `pulp_href` before using the following commands.

## Inspect Staged Content

Use the repository's `pulp_href` followed by `staging/` to list staged content URLs.
The list is paginated with `limit` and `offset`.
An empty list returns `{"count": 0, "next": null, "previous": null, "results": []}`.
`HEAD` on `staging/` returns `200` when staging is enabled.

To retrieve one staged content unit by path, append its `relative_path` to `staging/`.
Set `RELATIVE_PATH` to the staged content unit's relative path before using the path commands.

```bash
# List staged content URLs.
http --auth "admin:$PULP_PASSWORD" GET \
  "$PULP_API_URL/repositories/file/file/${REPOSITORY_ID}/staging/" \
  limit==20 offset==0

# Check whether staging is enabled.
http --auth "admin:$PULP_PASSWORD" HEAD \
  "$PULP_API_URL/repositories/file/file/${REPOSITORY_ID}/staging/"

# Retrieve content at a relative path, or check whether it exists.
http --auth "admin:$PULP_PASSWORD" GET \
  "$PULP_API_URL/repositories/file/file/${REPOSITORY_ID}/staging/${RELATIVE_PATH}/"
http --auth "admin:$PULP_PASSWORD" HEAD \
  "$PULP_API_URL/repositories/file/file/${REPOSITORY_ID}/staging/${RELATIVE_PATH}/"
```

The response contains the content unit's `pulp_href` and plugin-specific fields.
Nested paths remain part of `relative_path`; URL-encode reserved characters.
`GET` and `HEAD` return `404` when the path is not staged.

## Commit or Discard Staged Content

Commit staged content to create a new repository version when the content changes, or discard all staged content without creating a version:

```bash
# Commit staged content.
http --auth "admin:$PULP_PASSWORD" POST \
  "$PULP_API_URL/repositories/file/file/${REPOSITORY_ID}/staging/?action=commit"

# Discard staged content.
http --auth "admin:$PULP_PASSWORD" POST \
  "$PULP_API_URL/repositories/file/file/${REPOSITORY_ID}/staging/?action=restore"
```

If staging contains content, either action returns `202 Accepted` with a task URL in the `task` field.

Wait for that task to complete before checking the repository version or staging area.
If staging is empty, either action returns `204 No Content` and creates no task.
