#!/bin/bash

# WARNING: DO NOT EDIT!
#
# This file was generated by plugin_template, and is managed by it. Please use
# './plugin-template --travis pulpcore' to update this file.
#
# For more info visit https://github.com/pulp/plugin_template

set -euv

# skip this check for everything but PRs
if [ "$TRAVIS_PULL_REQUEST" = "false" ]; then
  exit 0
fi

# Switch to using ".." for git log to capture only PR commits
RANGE=`echo $TRAVIS_COMMIT_RANGE | sed 's/\.\.\./../'`

for sha in `git log --format=oneline --no-merges "$RANGE" | cut '-d ' -f1`
do
  pip install requests
  python .travis/validate_commit_message.py $sha
  VALUE=$?

  if [ "$VALUE" -gt 0 ]; then
    exit $VALUE
  fi
done
