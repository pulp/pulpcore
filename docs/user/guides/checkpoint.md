# Create and Distribute Checkpoints

!!! warning

    This feature requires plugin support to work correctly.

!!! warning

    This feature is provided as a tech preview and could change in backwards incompatible
    ways in the future.

## Overview

Checkpoints in Pulp provide a way to access and manage historical versions of repositories. This
feature allows users to view and install packages as they existed at specific points in time. By
using checkpoints, you can recreate environments from any given date/time, which is particularly
useful for tracking down when changes or regressions were introduced.

Checkpoints support reproducible deployments, help identify changes in package behavior over time,
and facilitate a structured update workflow. This ensures that a validated environment can be
consistently replicated across different stages of development and production.

For a similar concept, you can refer to [Debian's snapshot archive](https://snapshot.debian.org/),
which offers access to old snapshots of the repositories based on timestamps.

## Enabling Checkpoints

Checkpoint is a plugin-dependent feature. It needs to be enabled in a plugin before you can start
using it.

## Creating Checkpoints

The first step to start using checkpoint, is to create a checkpoint distribution which will be used
to distribute checkpoint publications. A checkpoint distribution serves all the checkpoint
publications of the related repository.

```bash
pulp file distribution create \
    --name <distro_name> \
    --repository <repo_name> \
    --base-path <distro_base_path> \
    --checkpoint
```

The next step is to create checkpoint publications. Only publications marked as checkpoint will be
served from the checkpoint distribution. When creating checkpoint publications, you can only pass
the repository, not any of its versions. The repository's latest version will be used to create the publication. Repository versions of the distributed checkpoint publications will be protected from
the automatic cleanup defined by `retain_repo_versions`.

```bash
pulp file publication create \
    --repository <repo_name> \
    --checkpoint
```

## Accessing Checkpoints

### Listing All Checkpoints

You can access a listing of all the available repository's checkpoint publications by accessing the
base path of any of the repository's checkpoint distributions.

```bash
http https://pulp.example/pulp/content/checkpoint/myfile
```

```html
<html>
<head><title>Index of checkpoint/myfile/</title></head>
<body bgcolor="white">
<h1>Index of checkpoint/myfile/</h1>
<hr><pre><a href="../">../</a>
<a href="20250130T203000Z/">20250130T203000Z/</a>                                  30-Jan-2025 20:30
<a href="20250130T205000Z/">20250130T205000Z/</a>                                  30-Jan-2025 20:50
</pre><hr></body>
</html>
```

### Accessing a Specific Checkpoint

To access a specific checkpoint, suffix the checkpoint distribution's path with a timestamp in the format
`yyyyMMddTHHmmssZ` (e.g. 20250130T205339Z), If a checkpoint was created at this time, it will be
served. Otherwise, you will be redirected to the latest checkpoint created before this timestamp.
Trying to access a checkpoint using a timestamp in the future or before the first checkpoint's
timestamp, will result in a 404 response.

Assuming the checkpoints from the above example, the below table show responses for sample requests

<table>
  <tr>
    <th>Request path</th>
    <th>Response</th>
  </tr>
  <tr>
    <td>checkpoint/myfile/20250130T203000Z/</td>
    <td>200</td>
  </tr>
  <tr>
    <td>checkpoint/myfile/20250130T204000Z/</td>
    <td>
    301 <br>
    Location: checkpoint/myfile/20250130T203000Z/
    </td>
  </tr>
  <tr>
    <td>checkpoint/myfile/20250130T206000Z/</td>
    <td>
    301 <br>
    Location: checkpoint/myfile/20250130T205000Z/
    </td>
  </tr>
  <tr>
    <td>checkpoint/myfile/20250130T202000Z/</td>
    <td>
    404
    </td>
  </tr>
  <tr>
    <td>checkpoint/myfile/29250130T203000Z/</td>
    <td>
    404
    </td>
  </tr>
</table>
