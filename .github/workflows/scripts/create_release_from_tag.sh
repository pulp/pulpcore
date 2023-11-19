#!/bin/sh
set -eu

curl -s -X "POST https://api.github.com/repos/$GITHUB_REPOSITORY/releases" \
-H "Authorization: token $RELEASE_TOKEN" \
-d @- << EOF
{
  "tag_name": "$1",
  "name": "$1"
}
EOF
