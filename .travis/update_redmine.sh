#!/bin/bash

set -euv

export COMMIT_MSG=$(git log --format=%B --no-merges -1)
export RELEASE=$(echo $COMMIT_MSG | awk '{print $2}')
export MILESTONE_URL=$(echo $COMMIT_MSG | awk '{print $6}')
export REDMINE_QUERY_URL=$(echo $COMMIT_MSG | awk '{print $4}')

echo "Releasing $RELEASE"
echo "Milestone URL: $MILESTONE_URL"
echo "Query: $REDMINE_QUERY_URL"

MILESTONE=$(http $MILESTONE_URL | jq -r .version.name)
echo "Milestone: $MILESTONE"

if [[ "$MILESTONE" != "$RELEASE" ]]; then
  echo "Milestone $MILESTONE is not equal to Release $RELEASE"
  exit 1
fi

pip install python-redmine
python .travis/redmine.py $REDMINE_QUERY_URL
