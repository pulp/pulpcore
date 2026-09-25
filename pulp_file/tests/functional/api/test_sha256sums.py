"""Tests that publish SHA256SUMS files alongside file plugin content."""

import pytest
import requests

RELATIVE_PATHS = ["release.iso", "docs/intro.md", "docs/api/reference.md"]


@pytest.fixture
def sha256sums_repository_factory(
    file_bindings, file_repository_factory, file_content_unit_with_name_factory, monitor_task
):
    """A factory to generate a repository holding a file at each of RELATIVE_PATHS."""

    def _sha256sums_repository_factory(**body):
        repository = file_repository_factory(**body)
        units = [file_content_unit_with_name_factory(path) for path in RELATIVE_PATHS]
        monitor_task(
            file_bindings.RepositoriesFileApi.modify(
                repository.pulp_href, {"add_content_units": [unit.pulp_href for unit in units]}
            ).task
        )
        return repository, {unit.relative_path: unit.sha256 for unit in units}

    return _sha256sums_repository_factory


@pytest.fixture
def sha256sums_distribution_factory(
    sha256sums_repository_factory, file_distribution_factory, distribution_base_url
):
    """A factory to generate an autopublished distribution of such a repository."""

    def _sha256sums_distribution_factory(**body):
        repository, digests = sha256sums_repository_factory(autopublish=True, **body)
        distribution = file_distribution_factory(repository=repository.pulp_href)
        return distribution_base_url(distribution.base_url), digests

    return _sha256sums_distribution_factory


def get_sha256sums(base_url, directory=""):
    """Return the entries of the SHA256SUMS in `directory`, or None if it is not served."""
    response = requests.get(f"{base_url}{directory}SHA256SUMS")
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return {tuple(line.split("  ")) for line in response.text.splitlines()}


@pytest.mark.parallel
def test_disabled_by_default(sha256sums_distribution_factory):
    base_url, _ = sha256sums_distribution_factory()

    assert get_sha256sums(base_url) is None


@pytest.mark.parallel
def test_root(sha256sums_distribution_factory):
    base_url, digests = sha256sums_distribution_factory(sha256sums="root")

    assert get_sha256sums(base_url) == {(digest, path) for path, digest in digests.items()}
    assert get_sha256sums(base_url, "docs/") is None
    assert get_sha256sums(base_url, "docs/api/") is None


@pytest.mark.parallel
def test_directory(sha256sums_distribution_factory):
    base_url, digests = sha256sums_distribution_factory(sha256sums="directory")

    assert get_sha256sums(base_url) == {(digest, path) for path, digest in digests.items()}
    assert get_sha256sums(base_url, "docs/") == {
        (digests["docs/intro.md"], "intro.md"),
        (digests["docs/api/reference.md"], "api/reference.md"),
    }
    assert get_sha256sums(base_url, "docs/api/") == {
        (digests["docs/api/reference.md"], "reference.md")
    }


@pytest.mark.parallel
def test_publication_defaults_to_repository(
    sha256sums_repository_factory, file_publication_factory
):
    repository, _ = sha256sums_repository_factory(sha256sums="directory")

    publication = file_publication_factory(repository=repository.pulp_href, sha256sums="root")
    assert publication.sha256sums == "root"

    publication = file_publication_factory(repository=repository.pulp_href)
    assert publication.sha256sums == "directory"
