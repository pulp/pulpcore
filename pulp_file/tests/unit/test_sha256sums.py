import pytest

from pulp_file.manifest import Entry, Sha256Sums

ENTRIES = [
    Entry(relative_path="release.iso", digest="a" * 64, size=1),
    Entry(relative_path="docs/intro.md", digest="b" * 64, size=2),
    Entry(relative_path="docs/api/reference.md", digest="c" * 64, size=3),
]


def read_written(written):
    return {path: open(local_path).read() for path, local_path in written.items()}


def test_root(tmp_path):
    written = Sha256Sums().write(ENTRIES, str(tmp_path))

    assert read_written(written) == {
        "SHA256SUMS": (
            f"{'a' * 64}  release.iso\n"
            f"{'b' * 64}  docs/intro.md\n"
            f"{'c' * 64}  docs/api/reference.md\n"
        )
    }


def test_per_directory(tmp_path):
    written = Sha256Sums(per_directory=True).write(ENTRIES, str(tmp_path))

    assert read_written(written) == {
        "SHA256SUMS": (
            f"{'a' * 64}  release.iso\n"
            f"{'b' * 64}  docs/intro.md\n"
            f"{'c' * 64}  docs/api/reference.md\n"
        ),
        "docs/SHA256SUMS": f"{'b' * 64}  intro.md\n{'c' * 64}  api/reference.md\n",
        "docs/api/SHA256SUMS": f"{'c' * 64}  reference.md\n",
    }


@pytest.mark.parametrize("per_directory", [False, True])
def test_no_entries(tmp_path, per_directory):
    assert Sha256Sums(per_directory=per_directory).write([], str(tmp_path)) == {}


def test_entries_without_digest_are_skipped(tmp_path):
    entries = ENTRIES + [Entry(relative_path="docs/ondemand.md", digest=None, size=4)]

    written = Sha256Sums(per_directory=True).write(entries, str(tmp_path))

    assert "ondemand.md" not in read_written(written)["docs/SHA256SUMS"]
