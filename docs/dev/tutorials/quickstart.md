# Contributing with code

## Overview

The purpose of this quickstart is to get yourself familiar with the usual contributing process in Pulp.
It assumes you are familiar with Pulp concepts and architecture.

## Workflow

### 1. Setup a dev environment

We have a dedicated tool to quickly setup a Pulp instance for development called [oci-env](https://github.com/pulp/oci_env).
It is a CLI tool that uses `docker/podman-compose` and [Pulp OCI Images](https://github.com/pulp/pulp-oci-images) and provides some convenient configuration options.

To set it up, follow these steps:

```bash
# 1. clone repos to the same basedir (pulpcore is required)
git clone https://github.com/pulp/oci_env.git
git clone https://github.com/pulp/pulpcore.git
git clone https://github.com/pulp/pulp_rpm.git

# 2. install oci-env client
cd oci_env
pip3 install -e client

# 3. use minimal compose.env
cp compose.env.example compose.env

# 4. build the images and do basic setup
oci-env compose build
oci-env generate-client -i
oci-env generate-client -i pulp_file

# 5. start the service
oci-env compose up 
```

A more comprehensive guide on setting up the dev environment is documented [here](#).

### 2. Make and test changes

Make the necessary changes and write good tests for them.

Then, run the test suite with:

```bash
# the -i (install) flag is required only for the first run
oci-env test -i -p pulp_rpm functional

# also, you can pass any pytest arguments here 
oci-env test -p pulp_rpm functional -k test_mychages
```

A more comprehensive guide on running tests is documented [here](#).

### 3. Update the changelog entry

Pulp uses [towncrier](#) to manage its changelog.

It requires that you have a related GitHub issue number, except for trivial changes (such as typo fixes).
In those cases the entry is no required at all.

The changelog message should use past simple tense and describe the change being made (as opposed to the problem or user story). Creating an entry can look something like this:

=== "For User-Facing changes"

    ```bash
    # create entry file
    touch CHANGES/3245.feature

    # write a message using past simple tense
    echo "Added API that allows users to export a repository version to disk." > CHANGES/3245.feature
    ```

=== "For Plugin API changes"

    ```bash
    # create entry file
    touch CHANGES/plugin_api/3245.bugfix

    # write a message using past simple tense
    echo "Added API that allows users to export a repository version to disk." > CHANGES/plugin_api/3245.feature
    ```

A more comprehensive guide on using towncrier in the Pulp project is documented [here](#).

### 4. Commit and Submit a PR

Commit messages in Pulp should contain a human readable explanation of what was fixed.
Here are general guidelines:

| extension | description                                                                                                                                                                                                                                      |
| --------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Title     | - Should be wrapped at about 50 chars                                                                                                                                                                                                            |
| Body      | - Should be wrapped at wrapped at 72 characters                                                                                                                                                                                                  |
|           | - May be broken up into paragraphs.                                                                                                                                                                                                              |
| Footer    | - Should Linked issue on the plugin Github Issue tracker. See the [Github Linking Docs](https://docs.github.com/en/issues/tracking-your-work-with-issues/linking-a-pull-request-to-an-issue#linking-a-pull-request-to-an-issue-using-a-keyword). |

For more on what constitutes a good commit message, we recommend [Tim Pope’s blog post on the subject](http://tbaggery.com/2008/04/19/a-note-about-git-commit-messages.html). Putting this all together, the following is an example of a good commit message:

```
Update install and quickstart

The install docs and quickstart was leaving out an important step on
the worker configuration.

closes #1392
```

A more comprehensive guide on using git in the Pulp project is documented [here](#).
