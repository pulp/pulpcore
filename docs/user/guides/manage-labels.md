# Manage Labels

Pulp provides a way to add key/value data to many resources (e.g. repositories, remotes,
distributions) in the form of labels. Labels are also useful for categorizing and filtering
resources. In the API, labels appear as a dictionary field that maps keys (strings) to values (also
strings).

## Creating labels

To create labels:

```bash
# create a new repository
pulp file repository create --name myrepo

# set some labels
pulp file repository label set --name myrepo --key environment --value production
pulp file repository label set --name myrepo --key reviewed --value true

# call show to view the repo's labels
pulp file repository show --name myrepo
```

On show, you should see the new labels that have been created:

```json
{
  "pulp_href": "/pulp/api/v3/repositories/file/file/13477a92-b811-4436-a76a-d2469a17a62e/",
  "pulp_created": "2021-01-29T17:54:17.084105Z",
  "versions_href":
  "/pulp/api/v3/repositories/file/file/13477a92-b811-4436-a76a-d2469a17a62e/versions/",
  "pulp_labels": {
    "environment": "production",
    "reviewed": "true"
  },
  "latest_version_href": "/pulp/api/v3/repositories/file/file/13477a92-b811-4436-a76a-d2469a17a62e/versions/0/",
  "name": "myrepo",
  "description": null,
  "remote": null
}
```

## Updating labels

To update an existing label, call set again:

```bash
# update the label
pulp file repository label set --name myrepo --key reviewed --value false

# call show to view the repo's labels
pulp file repository show --name myrepo
```

On show, you should now see:

```json
{
  "pulp_href": "/pulp/api/v3/repositories/file/file/13477a92-b811-4436-a76a-d2469a17a62e/",
  "pulp_created": "2021-01-29T17:54:17.084105Z",
  "versions_href": "/pulp/api/v3/repositories/file/file/13477a92-b811-4436-a76a-d2469a17a62e/versions/",
  "pulp_labels": {
    "environment": "production",
    "reviewed": "false"
  },
  "latest_version_href": "/pulp/api/v3/repositories/file/file/13477a92-b811-4436-a76a-d2469a17a62e/versions/0/",
  "name": "myrepo",
  "description": null,
  "remote": null
}
```

## Unsetting labels

To remove a label from a resource, call the unset command:

```bash
# update the label
pulp file repository label unset --name myrepo --key reviewed

# call show to view the repo's labels
pulp file repository show --name myrepo
```

On show, you should now see:

```json
{
  "pulp_href": "/pulp/api/v3/repositories/file/file/13477a92-b811-4436-a76a-d2469a17a62e/",
  "pulp_created": "2021-01-29T17:54:17.084105Z",
  "versions_href": "/pulp/api/v3/repositories/file/file/13477a92-b811-4436-a76a-d2469a17a62e/versions/",
  "pulp_labels": {
    "environment": "production"
  },
  "latest_version_href": "/pulp/api/v3/repositories/file/file/13477a92-b811-4436-a76a-d2469a17a62e/versions/0/",
  "name": "myrepo",
  "description": null,
  "remote": null
}
```

## Filtering

Pulp provides a `pulp_label_select` field for filtering resources by label. The value for this
field must be url-encoded. The following operations are supported:

- `environment=production` - label has key 'environment' with value 'production'
- `environment!=production` - label has key 'environment' without value 'production'
- `environment~prod` - label has key 'environment' with value that contains 'prod' (case insensitive)
- `enviroment` - label has key of environment
- `!environment` - label without a key of environment

Multiple terms can be combined with `,`:

- `environment=production,reviewed=true` - returns resources with labels where environment is
  production and reviewed is true
- `environment,reviewed=false` - returns resources with an environment label and where reviewed is
  false

To filter using the CLI use `--label-select`:

```bash
pulp file repository list --label-select="environment~prod,reviewed"
```

This would return a list of repositories such as:

```json
{
  "pulp_href": "/pulp/api/v3/repositories/file/file/13477a92-b811-4436-a76a-d2469a17a62e/",
  "pulp_created": "2021-01-29T17:54:17.084105Z",
  "versions_href": "/pulp/api/v3/repositories/file/file/13477a92-b811-4436-a76a-d2469a17a62e/versions/",
  "pulp_labels": {
    "environment": "production",
    "reviewed": "true"
  },
  "latest_version_href": "/pulp/api/v3/repositories/file/file/13477a92-b811-4436-a76a-d2469a17a62e/versions/0/",
  "name": "myrepo",
  "description": null,
  "remote": null
}
```
