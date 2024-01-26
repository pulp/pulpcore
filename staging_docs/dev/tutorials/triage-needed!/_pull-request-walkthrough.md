# Pull Request Walkthrough

Changes to pulpcore are submitted via [GitHub Pull Requests (PR)](https://help.github.com/articles/about-pull-requests/) to the [pulp git repository](https://github.com/pulp/pulpcore) . Plugin git repositories are listed in the [plugin table](https://pulpproject.org/content-plugins/).

## Checklist

1. Add `functional tests` or `unit tests` where appropriate and ensure tests
   are passing on the CI.
2. Add a `CHANGES entry <changelog-update>`.
3. Update relevent {doc}`documentation`. Please build the docs to test!
4. `Rebase and squash` to a single commit.
5. Write an excellent `commit-message`. Make sure you reference and link to the issue.
6. Push your branch to your fork and open a [Pull request across forks](https://help.github.com/articles/creating-a-pull-request-from-a-fork/).
7. If the change requires a corresponding change in pulp-cli, open a PR against the pulp-cli or
   {doc}`file an issue</bugs-features>`.

## Review

Before a pull request can be merged, the `tests` must pass and it must
be reviewed. We encourage you to `reach out to the developers` to get speedy review.

## To Cherry-Pick or Not

If you are fixing a bug that should also be backported to another branch than `main`, add the
backport label, .e.g `backport-3.18`. PR authors can also add or remove this label if they have
write access.
