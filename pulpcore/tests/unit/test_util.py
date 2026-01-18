import hashlib
import tempfile
import unittest
from pathlib import Path

import pytest
from unittest import mock

from pulpcore.app import models, util
from pulpcore.app.util import HashingFileWriter

pytestmark = pytest.mark.usefixtures("fake_domain")


def test_get_view_name_for_model_with_object():
    """
    Use Repository as an example that should work.
    """
    ret = util.get_view_name_for_model(models.Artifact(), "foo")
    assert ret == "artifacts-foo"


def test_get_view_name_for_model_with_model():
    """
    Use Repository as an example that should work.
    """
    ret = util.get_view_name_for_model(models.Artifact, "foo")
    assert ret == "artifacts-foo"


def test_get_view_name_for_model_not_found(monkeypatch):
    """
    Given an unknown viewset (in this case a Mock()), this should raise LookupError.
    """
    monkeypatch.setattr(util, "get_viewset_for_model", mock.Mock())
    with pytest.raises(LookupError):
        util.get_view_name_for_model(mock.Mock(), "foo")


class TestHashingFileWriter(unittest.TestCase):
    def setUp(self) -> None:
        self.test_dir_obj = tempfile.TemporaryDirectory()
        self.test_dir = Path(self.test_dir_obj.name)
        self.base_path = self.test_dir / "export.tar"

    def tearDown(self) -> None:
        self.test_dir_obj.cleanup()

    def test_chunk_size_zero_creates_single_file(self) -> None:
        """Verify chunk_size=0 creates one file with no suffix."""
        data = b"x" * 1024

        with HashingFileWriter(self.base_path, hasher_cls=hashlib.sha256, chunk_size=0) as writer:
            writer.write(data)

        self.assertTrue(self.base_path.exists())
        self.assertFalse((self.base_path.parent / "export.tar.0000").exists())

        self.assertEqual(self.base_path.read_bytes(), data)
        expected_hash = hashlib.sha256(data).hexdigest()
        self.assertEqual(writer.results[str(self.base_path)], expected_hash)

    def test_exact_boundary_split(self) -> None:
        """
        If we write exactly chunk_size, we should have 1 file.
        Only if we write 1 byte MORE should we get a second file.
        """
        chunk = 10
        data = b"A" * 10

        with HashingFileWriter(
            self.base_path, hasher_cls=hashlib.sha256, chunk_size=chunk
        ) as writer:
            writer.write(data)

        # Should be exactly 1 file: .0000
        self.assertTrue((self.test_dir / "export.tar.0000").exists())
        self.assertFalse((self.test_dir / "export.tar.0001").exists())
        self.assertEqual((self.test_dir / "export.tar.0000").stat().st_size, 10)

    def test_overflow_boundary_split(self) -> None:
        """Writing chunk_size + 1 bytes should create two files."""
        chunk = 10
        data = b"A" * 11

        with HashingFileWriter(
            self.base_path, hasher_cls=hashlib.sha256, chunk_size=chunk
        ) as writer:
            writer.write(data)

        f0 = self.test_dir / "export.tar.0000"
        f1 = self.test_dir / "export.tar.0001"

        self.assertTrue(f0.exists())
        self.assertTrue(f1.exists())
        self.assertEqual(f0.stat().st_size, 10)
        self.assertEqual(f1.stat().st_size, 1)

    def test_hasher_content(self) -> None:
        """Ensure we can swap the hasher (e.g., md5)."""
        data = b"check"
        with HashingFileWriter(self.base_path, hasher_cls=hashlib.md5, chunk_size=0) as writer:
            writer.write(data)

        expected = hashlib.md5(data).hexdigest()
        self.assertEqual(writer.results[str(self.base_path)], expected)

    def test_nested_directory_creation(self) -> None:
        """Ensure it creates parent directories if they don't exist."""
        nested_path = self.test_dir / "subdir" / "deep" / "archive.tar"

        with HashingFileWriter(nested_path, hasher_cls=hashlib.sha256, chunk_size=0) as writer:
            writer.write(b"content")

        self.assertTrue(nested_path.exists())

    def test_multiple_writes_cross_boundary(self) -> None:
        """Verify multiple small writes correctly trigger file rotation."""
        chunk = 10
        # 3 writes of 4 bytes = 12 bytes total. Should create 2 files.
        with HashingFileWriter(
            self.base_path, hasher_cls=hashlib.sha256, chunk_size=chunk
        ) as writer:
            writer.write(b"aaaa")
            writer.write(b"bbbb")
            writer.write(b"cccc")

        f0, f1 = self.test_dir / "export.tar.0000", self.test_dir / "export.tar.0001"
        self.assertEqual(f0.read_bytes(), b"aaaabbbbcc")
        self.assertEqual(f1.read_bytes(), b"cc")

    def test_results_insertion_order(self) -> None:
        """Verify the results dictionary preserves the order of file creation."""
        chunk = 5
        data = b"123456789012345"  # 15 bytes, 3 chunks
        with HashingFileWriter(
            self.base_path, hasher_cls=hashlib.sha256, chunk_size=chunk
        ) as writer:
            writer.write(data)

        expected_keys = [
            str(self.base_path.with_name("export.tar.0000")),
            str(self.base_path.with_name("export.tar.0001")),
            str(self.base_path.with_name("export.tar.0002")),
        ]
        self.assertEqual(list(writer.results.keys()), expected_keys)

    def test_write_empty_bytes(self) -> None:
        """Ensure writing empty bytes doesn't create a file or change state."""
        with HashingFileWriter(self.base_path, hasher_cls=hashlib.sha256, chunk_size=10) as writer:
            writer.write(b"")

        # No file should be created if no data was ever actually written
        self.assertEqual(len(writer.results), 0)
        self.assertFalse(self.base_path.exists())

    def test_large_chunk_rotation(self) -> None:
        """Verify data much larger than chunk_size splits into many files."""
        chunk = 10
        data = b"X" * 35  # Should create 0000, 0001, 0002, 0003
        with HashingFileWriter(
            self.base_path, hasher_cls=hashlib.sha256, chunk_size=chunk
        ) as writer:
            writer.write(data)

        self.assertEqual(len(writer.results), 4)
        self.assertEqual((self.test_dir / "export.tar.0003").stat().st_size, 5)
