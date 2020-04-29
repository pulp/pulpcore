from unittest import TestCase

from pulpcore.app.files import validate_file_paths


class TestValidateFilePaths(TestCase):
    def test_valid_paths(self):
        """
        Test for valid paths.
        """
        paths = ["a/b", "a/c/b", "PULP_MANIFEST", "b"]
        validate_file_paths(paths)

        paths = ["a/b/c", "a/b/d"]
        validate_file_paths(paths)

    def test_dupes(self):
        """
        Test for two duplicate paths.
        """
        paths = ["a/b", "PULP_MANIFEST", "PULP_MANIFEST"]
        with self.assertRaisesRegex(ValueError, "Path is duplicated: PULP_MANIFEST"):
            validate_file_paths(paths)

    def test_overlaps(self):
        """
        Test for overlapping paths.
        """
        paths = ["a/b", "a/b/c"]
        with self.assertRaises(ValueError):
            validate_file_paths(paths)

        paths = ["a/b/c", "a/b"]
        with self.assertRaises(ValueError):
            validate_file_paths(paths)

        paths = ["b/c", "a/b", "b"]
        with self.assertRaises(ValueError):
            validate_file_paths(paths)

        paths = ["a/b/c/d", "a/b"]
        with self.assertRaises(ValueError):
            validate_file_paths(paths)

        paths = ["a/b", "a/b/c/d"]
        with self.assertRaises(ValueError):
            validate_file_paths(paths)
