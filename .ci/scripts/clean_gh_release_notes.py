#!/usr/bin/env python3
# This script is running with elevated privileges from the main branch against pull requests.
#
# It cleans the input from artifacts which are used by the pulp documentation internally,
# but clutter for GitHub releases

import sys

NOTE = """
> [!NOTE]
> Official changes are available on [Pulp docs]({docs_url})\
"""


def main():
    plugin_name = sys.argv[1]
    version_str = sys.argv[2]
    docs_url = f"https://pulpproject.org/{plugin_name}/changes/#{version_str}"
    note_added = False
    for line in sys.stdin:
        if line.endswith("\n"):
            line = line[:-1]
        if line.startswith("#"):
            print(line.split(" {: #")[0])
            if not note_added and version_str in line:
                print(NOTE.format(docs_url=docs_url))
                note_added = True
        else:
            print(line)


if __name__ == "__main__":
    main()
