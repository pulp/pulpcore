import pytest

from pulpcore.app.files import validate_file_paths


def test_valid_paths():
    """
    Test for valid paths.
    """
    paths = ["a/b", "a/c/b", "PULP_MANIFEST", "b"]
    validate_file_paths(paths)

    paths = ["a/b/c", "a/b/d"]
    validate_file_paths(paths)


def test_dupes():
    """
    Test for two duplicate paths.
    """
    paths = ["a/b", "PULP_MANIFEST", "PULP_MANIFEST"]
    with pytest.raises(ValueError, match="Path errors found. Paths are duplicated: PULP_MANIFEST"):
        validate_file_paths(paths)


def test_overlaps():
    """
    Test for overlapping paths.
    """
    paths = ["a/b", "a/b/c"]
    with pytest.raises(ValueError):
        validate_file_paths(paths)

    paths = ["a/b/c", "a/b"]
    with pytest.raises(ValueError):
        validate_file_paths(paths)

    paths = ["b/c", "a/b", "b"]
    with pytest.raises(ValueError):
        validate_file_paths(paths)

    paths = ["a/b/c/d", "a/b"]
    with pytest.raises(ValueError):
        validate_file_paths(paths)

    paths = ["a/b", "a/b/c/d"]
    with pytest.raises(ValueError):
        validate_file_paths(paths)
