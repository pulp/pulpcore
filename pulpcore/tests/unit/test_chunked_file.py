import json
import typing as t
from pathlib import Path

import pytest
from rest_framework.exceptions import ValidationError

from pulpcore.app.models import ProgressReport
from pulpcore.app.tasks.importer import ChunkedFile
from pulpcore.app.util import Crc32Hasher, compute_file_hash


def write_chunk_files(tmp_path: Path, data_chunks: t.List[t.ByteString]):
    """Utility to generate chunk-files fixtures"""
    files = {}

    for i, chunk_bytes in enumerate(data_chunks):
        filename = f"myfile.{i:02}"
        chunk_path = tmp_path / filename
        chunk_path.write_bytes(chunk_bytes)
        files[chunk_path.name] = compute_file_hash(chunk_path, hasher=Crc32Hasher())

    return files


def create_tocfile(
    tmp_path: Path, data_chunks: t.List[t.ByteString], chunk_size: int, corrupted: bool = False
):
    """
    Utility to generate a tocfile.json and return its path.

    It can optionally generate a corrupted toc-file with wrong first checksum.

    Its basic form is:

    ```json
    {
        "files": {
            "base-filename.00": "crc32-digest",
            ...
            "base-filename.NN": "crc32-digest",
        },
        "meta": {
            "chunk_size": 1024,
        }
    }
    ```
    """
    files = write_chunk_files(tmp_path, data_chunks=data_chunks)
    tocfile_path = tmp_path / "tocfile.json"

    if corrupted is True:
        first_chunk_name = list(files.keys())[0]
        files[first_chunk_name] = "invalid-checksum"

    toc_content = {
        "files": files,
        "meta": {"chunk_size": chunk_size},
    }
    with open(tocfile_path, "w") as file:
        json.dump(toc_content, file)

    return tocfile_path


@pytest.mark.parametrize(
    "chunks_list,chunk_size",
    [
        pytest.param([b"1234", b"5678", b"abcd", b"edfg"], 4, id="Full last chunk"),
        pytest.param([b"1234", b"5678", b"abcd", b"e"], 4, id="Partial last chunk"),
        pytest.param([b"123", b"567", b"abc", b"efg"], 3, id="Different chunk_size"),
        pytest.param([b"1234"], 4, id="Single full chunk"),
        pytest.param([b"12"], 4, id="Single partial chunk"),
    ],
)
def test_chunked_file_fileobj_api(tmp_path, chunks_list, chunk_size):
    """Methods tell, read and seek works inside context manager"""
    contiguous_data = b"".join(chunks_list)

    toc_path = create_tocfile(tmp_path, data_chunks=chunks_list, chunk_size=chunk_size)
    chunked_file = ChunkedFile(toc_path)

    with chunked_file as fp:
        # read byte-per-byte
        assert fp.tell() == 0
        for i, byte in enumerate(contiguous_data):
            assert fp.tell() == i
            assert fp.read(1)[0] == byte

        # reset and repeat
        fp.seek(0)
        for i, byte in enumerate(contiguous_data):
            assert fp.tell() == i
            assert fp.read(1)[0] == byte

        # read by chunk size
        fp.seek(0)
        for i, chunk in enumerate(chunks_list):
            assert fp.tell() == i * chunk_size
            assert fp.read(chunk_size) == chunk

        # read all at once
        fp.seek(0)
        content_size = len(contiguous_data)
        assert fp.read(content_size) == contiguous_data

        # read more than available
        fp.seek(0)
        data = fp.read(len(contiguous_data) - 1)
        assert data + fp.read(5) == contiguous_data


def test_chunked_file_validate(tmp_path, monkeypatch):
    monkeypatch.setattr(ProgressReport, "save", lambda *args, **kwargs: None)

    chunks_list = [b"1234", b"5678", b"abcd", b"edfg"]
    chunk_size = 4

    toc_path = create_tocfile(tmp_path, data_chunks=chunks_list, chunk_size=chunk_size)
    chunked_file = ChunkedFile(toc_path)
    chunked_file.validate_chunks()


def test_chunked_file_validate_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(ProgressReport, "save", lambda *args, **kwargs: None)

    chunks_list = [b"1234", b"5678", b"abcd", b"edfg"]
    chunk_size = 4

    toc_path = create_tocfile(
        tmp_path, data_chunks=chunks_list, chunk_size=chunk_size, corrupted=True
    )
    chunked_file = ChunkedFile(toc_path)
    with pytest.raises(ValidationError, match="Import chunk hash mismatch.*"):
        chunked_file.validate_chunks()


def test_chunked_file_shortread_exception(tmp_path):
    """Raises when there is a shorter chunk which isnt the last one."""
    malformed_chunks_list = [b"1234", b"567", b"abcd", b"edfg"]
    chunk_size = 4
    contiguous_data = b"".join(malformed_chunks_list)

    toc_path = create_tocfile(tmp_path, data_chunks=malformed_chunks_list, chunk_size=chunk_size)
    chunked_file = ChunkedFile(toc_path)

    with pytest.raises(Exception, match=r"Short read from chunk \d*."):
        with chunked_file as fp:
            content_size = len(contiguous_data)
            fp.read(content_size)
