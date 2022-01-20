#!/bin/bash

# WARNING: DO NOT EDIT!
#
# This file was generated by plugin_template, and is managed by it. Please use
# './plugin-template --github pulpcore' to update this file.
#
# For more info visit https://github.com/pulp/plugin_template

# make sure this script runs at the repo root
cd "$(dirname "$(realpath -e "$0")")"/../..

set -euv

export COMMIT_MSG=$(git log --format=%B --no-merges -1)
export RELEASE=$(echo $COMMIT_MSG | awk '{print $2}')
export MILESTONE_URL=$(echo $COMMIT_MSG | grep -o "Redmine Milestone: .*" | awk '{print $3}')
export REDMINE_QUERY_URL=$(echo $COMMIT_MSG | grep -o "Redmine Query: .*" | awk '{print $3}')

echo "Releasing $RELEASE"
echo "Milestone URL: $MILESTONE_URL"
echo "Query: $REDMINE_QUERY_URL"

pip install python-redmine httpie

python3 .ci/scripts/redmine.py $REDMINE_QUERY_URL $MILESTONE_URL $RELEASE
