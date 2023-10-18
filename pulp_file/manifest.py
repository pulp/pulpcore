from collections import namedtuple

from gettext import gettext as _

from re import fullmatch


Line = namedtuple("Line", ("number", "content"))


class Entry:
    """
    Manifest entry.

    Format: <relative_path>,<digest>,<size>.
    Lines beginning with `#` are ignored.

    Attributes:
        relative_path (str): A relative path.
        digest (str): The file sha256 hex digest.
        size (int): The file size in bytes.

    """

    def __init__(self, relative_path, size, digest):
        """
        Create a new Entry.

        Args:
            relative_path (str): A relative path.
            digest (str): The file sha256 hex digest.
            size (int): The file size in bytes.

        """
        self.relative_path = relative_path
        self.digest = digest
        self.size = size

    @staticmethod
    def parse(line):
        """
        Parse the specified line from the manifest into an Entry.

        Args:
            line (Line): A line from the manifest.

        Returns:
            Entry: An entry.

        Raises:
            ValueError: on parsing error.

        """
        all_parts = line.content.count(",") >= 2
        if all_parts:
            relative_path, digest, size = [s.strip() for s in line.content.rsplit(",", maxsplit=2)]
        if (
            not all_parts
            or not fullmatch(r"^[^/]+(/[^/]+)*$", relative_path)
            or not fullmatch(r"^[0-9a-fA-F]+$", digest)
            or not size.isdigit()
        ):
            raise ValueError(
                _(
                    "Error: Parsing of the manifest file failed on line:{n}.\n"
                    "Please make sure the remote URL is pointing to a valid manifest file.\n"
                    "The manifest file should be "
                    "composed of lines in the following format: <relative_path>,<digest>,<size>."
                ).format(n=line.number)
            )
        return Entry(relative_path=relative_path, digest=digest, size=int(size))

    def __str__(self):
        """
        Returns a string representation of the Manifest Entry.

        Returns:
            str: format: "<relative_path>,<digest>,<size>"

        """
        fields = [self.relative_path, self.digest]
        if isinstance(self.size, int):
            fields.append(str(self.size))
        return ",".join(fields)


class Manifest:
    """
    A file manifest.

    Describes files contained within the directory.

    Attributes:
        relative_path (str): An relative path to the manifest.

    """

    def __init__(self, relative_path):
        """
        Create a new Manifest.

        Args:
            relative_path (str): An relative path to the manifest.

        """
        self.relative_path = relative_path

    @staticmethod
    def parse(manifest_str):
        """
        Parse a manifest string and yield entries.

        Yields:
            Entry: for each line.

        """
        for n, line in enumerate(manifest_str.splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            if line.startswith("#"):
                continue
            yield Entry.parse(Line(number=n, content=line))

    def read(self):
        """
        Read the file at `relative_path` and yield entries.

        Yields:
            Entry: for each line.

        """
        with open(self.relative_path) as fp:
            yield from Manifest.parse(fp.read())

    def write(self, entries):
        """
        Write the manifest.

        Args:
            entries (iterable): The entries to be written.

        """
        with open(self.relative_path, "w+") as fp:
            for entry in entries:
                line = str(entry)
                fp.write(line)
                fp.write("\n")
