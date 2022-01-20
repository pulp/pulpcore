#!/bin/sh
set -e

BRANCH_NAME=$(echo $GITHUB_REF | sed -rn 's/refs\/heads\/(.*)/\1/p')

ref_string=$(git show-ref --tags | grep refs/tags/$1)

SHA=${ref_string:0:40}

remote_repo=https://pulpbot:${RELEASE_TOKEN}@github.com/${GITHUB_REPOSITORY}.git

git push "${remote_repo}" $BRANCH_NAME

curl -s -X POST https://api.github.com/repos/$GITHUB_REPOSITORY/git/refs \
-H "Authorization: token $RELEASE_TOKEN" \
-d @- << EOF
{
  "ref": "refs/tags/$1",
  "sha": "$SHA"
}
EOF
