# Contributing with docs

## Overview

The purpose of this quickstart is to help you to make docs-only contributing effortless, without requiring a full development setup.

## Workflow

### 1. Setup

Pulp uses a dedicated tool to aggregate documentation from its various repositories called [`pulp-docs`](site:pulp-docs/docs/dev/).

Once its installed, it'll look for local Pulp repo checkouts in the parent directory and, if not found,
it'll clone the last released repo from GitHub into a managed environment.

=== "pipx"

    ```bash
    pipx install git+https://github.com/pulp/pulp-docs --include-deps
    ```

=== "pip"

    ```bash
    pip install --user git+https://github.com/pulp/pulp-docs
    ```

=== "pip with venv"

    ```bash
    python -m venv venv
    source venv/bin/activate
    pip install git+https://github.com/pulp/pulp-docs
    ```

See also `pulp-docs` [Getting Started](site:pulp-docs/docs/dev/tutorials/getting-started/).

### 2. Make a change

Make your changes using markdown and supported `mkdocs-material` features.
See the [markdown cheat sheet].

Our docs comply with the [Diataxis framework] for organizing content.
Here is a brief summary:

|               | Tutorial                          | How-to Guide                      | Reference                 | Explanation               |
| ---           | ---                               | ---                               | ---                       | ---                       |
| **purpose**   | to provide a learning experience  | to help achieve a particular goal | to describe the machinery | to illuminate a topic     |
| **form**      | a lesson                          | a series of steps                 | dry description           | discursive explanation    |

Also, keep in mind that you are always writing primarily for one of the three types of `persona`:

- User: "I just want to create sync and publish repositories."
- Admin: "I need to get this instance configured and keep it running."
- Developer: "I need to add features, troubleshoot and fix bugs."

When you are done with your changes, you can preview it locally with:

```bash
pulp-docs serve
```

See also `pulp-docs` [Getting Started](site:pulp-docs/docs/dev/tutorials/getting-started/).

### 3. Update the changelog entry

Pulp uses [towncrier] to manage its changelog.

It requires that you have a related GitHub issue number, except for trivial changes (such as typo fixes).
In those cases the entry is not required at all.

The changelog message should use past simple tense and describe the change being made (as opposed to the problem or user story).
Creating an entry can look something like this:

=== "For User-Facing changes"

    ```bash
    # write a message using past simple tense
    echo "Added documentation for new pulpcore-manager command." > CHANGES/3245.doc
    ```

=== "For Plugin API changes"

    ```bash
    # write a message using past simple tense
    echo "Added documentation for new pulpcore plugin api." > CHANGES/plugin_api/3245.doc
    ```

A more comprehensive guide on using towncrier in the Pulp project is documented [here](site:/pulpcore/docs/dev/guides/git/#changelog-update).

### 4. Commit and Submit a PR

Commit messages in Pulp should contain a human readable explanation of what was fixed.
Here are general guidelines:

| Section       | description                                                                                           |
| ---           | ---                                                                                                   |
| Title         | - Should be wrapped at about 50 characters.                                                           |
| Body          | - Should be wrapped at 72 characters.                                                                 |
|               |    - May be broken up into paragraphs.                                                                |
| Footer        | - Should reference a linked issue on the plugin Github Issue tracker. See the [Github Linking Docs].  |

For more on what constitutes a good commit message, we recommend [Tim Pope’s blog post on the subject].
Putting this all together, the following is an example of a good commit message:

```
Update install and quickstart documentation

The install docs and quickstart was leaving out an important step on
the worker configuration.

closes #1392
```

A more comprehensive guide on using git in the Pulp project is documented [here](site:pulpcore/docs/dev/guides/git/).

[Diataxis framework]: https://diataxis.fr/map/
[Github Linking Docs]: https://docs.github.com/en/issues/tracking-your-work-with-issues/linking-a-pull-request-to-an-issue#linking-a-pull-request-to-an-issue-using-a-keyword
[markdown cheat sheet]: site:/pulp-docs/docs/dev/reference/markdown-cheatsheet
[Tim Pope’s blog post on the subject]: http://tbaggery.com/2008/04/19/a-note-about-git-commit-messages.html
[towncrier]: https://towncrier.readthedocs.io/en/stable/
