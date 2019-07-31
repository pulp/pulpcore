#!/bin/bash

# Prevent pip-installed /usr/local/bin/pulp-content from getting run instead of
# our /usr/bin/pulp script.
#
# We still want conatiner users to call command names, not paths, so we can
# change our scripts' locations in the future, and call special logic in this
# script based solely on the command name.
exec "/usr/bin/$@"
