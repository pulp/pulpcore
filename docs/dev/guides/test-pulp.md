# Write and run tests

There are two types of tests in *pulpcore* and in the plugins:

1. **Unittests** are meant to test the interface of a specific unit utilizing a test database.
2. **Functional tests** are meant to test certain workflows utilizing a running instance of pulp.

A pull request that has failing unit or functional tests cannot be merged.



## Unit Tests

New code is encouraged to have basic unit tests that demonstrate that
units (function, method or class instance) are working correctly.

The unit tests for `pulpcore` are in [pulpcore/tests](https://github.com/pulp/pulpcore/tree/master/pulpcore/tests/unit).



## Functional Tests

Functional tests verify a specific feature.
In general functional tests tend to answer the question "As an user can I do this?"

It is highly encouraged to accompany new features with functional
tests in [pulpcore/functional](https://github.com/pulp/pulpcore/tree/master/pulpcore/tests/functional).

Only the tests for features related to `pulpcore` should live in this repository.

Functional tests for features related to a specific plugin should live in the
plugin repository itself. For example:

- [File Plugin](https://github.com/pulp/pulpcore/tree/master/pulp_file/tests/functional)
- [RPM Plugin](https://github.com/pulp/pulp_rpm/tree/master/pulp_rpm/tests/functional)

## Prerequisites for running tests

If you want to run the functional tests, you need a running Pulp instance that is allowed to be
mixed up by the tests (in other words, running the tests on a production instance is not
recommended). For example, using the development vm (see `DevSetup`),
this can be accomplished by `workon pulp; pulpcore-manager runserver 24817`. The
`pulpcore-manager` command is `manage.py` configured with the
`DJANGO_SETTINGS_MODULE="pulpcore.app.settings"`.

### Using pulplift

When running one of the `pulp3-source-*` boxes in `pulplift`, all the services are running.  They
should be restarted with `prestart` if any pulp code (not test code) has been changed.

When testing S3 support, you can start and configure a local `minio` container with `pminio`.

Pulp functional tests use a set of upstream fixture repositories hosted on
[fixtures.pulpproject.org](https://fixtures.pulpproject.org/).  In case you want serve those
locally, you can run `pfixtures` which will execute a `nginx` container with a copy of those
fixtures.

For more info about Pulp development specific helper commands, you can consult `phelp`.

## Running tests

In case pulp is installed in a virtual environment, activate it first (`workon pulp`).

All tests of a plugin (or pulpcore itself) are run with `pulpcore-manager test <plugin_name>`.
This involves setting up (and tearing down) the test database, however the functional tests are
still performed against the configured pulp instance with its *production* database.

To only perform the unittests, you can skip the prerequisites and call
`pulpcore-manager test <plugin_name>.tests.unit`.

If you are only interested in functional tests, you can skip the creation of the test database by
using `pytest <path_to_plugin>/<plugin_name>/tests/functional`.

!!! note
    Make sure, the task runners are actually running. In doubt, run `prestart` or
    `systemctl restart pulpcore-worker@*`.


!!! note
    You can be more specific on which tests to run by calling something like
    `pulpcore-manager test pulp_file.tests.unit.test_models` or
    `py.test <path_to_plugin>/<plugin_name>/tests/functional/api/test_sync.py`.

### Environment variables

The following environment variables can be set to adjust the API configuration for
functional tests:

- `API_PROTOCOL` (default: "https")
- `API_HOST` (default: "pulp")
- `API_PORT` (default: "443")
- `ADMIN_USERNAME` (default: "admin"),
- `ADMIN_PASSWORD` (default: "password")

## Contributing to tests

A new version of Pulp will only be released when all unit and functional tests are
passing.

Contributing test is a great way to ensure that your workflows never regress.

[istqb]: https://www.istqb.org/downloads/syllabi/foundation-level-syllabus.html
