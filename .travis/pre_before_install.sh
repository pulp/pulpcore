#!/usr/bin/env bash
set -mveuo pipefail

export PULP_FILE_PR_NUMBER=$(echo $COMMIT_MSG | grep -oP 'Required\ PR:\ https\:\/\/github\.com\/pulp\/pulp_file\/pull\/(\d+)' | awk -F'/' '{print $7}')
export PULP_CERTGUARD_PR_NUMBER=$(echo $COMMIT_MSG | grep -oP 'Required\ PR:\ https\:\/\/github\.com\/pulp\/pulp-certguard\/pull\/(\d+)' | awk -F'/' '{print $7}')

pip install yq
PULP_FILE_BRANCH=$(yq -r .pulpcore_branch ./template_config.yml)
echo PULP_FILE_BRANCH="$PULP_FILE_BRANCH"

cd ..
git clone https://github.com/pulp/pulp_file.git --branch "$PULP_FILE_BRANCH"
if [ -n "$PULP_FILE_PR_NUMBER" ]; then
  cd pulp_file
  git fetch origin +refs/pull/$PULP_FILE_PR_NUMBER/merge
  git checkout FETCH_HEAD
  cd ..
fi

git clone https://github.com/pulp/pulp-certguard.git
if [ -n "$PULP_CERTGUARD_PR_NUMBER" ]; then
  cd pulp-certguard
  git fetch origin +refs/pull/$PULP_CERTGUARD_PR_NUMBER/merge
  git checkout FETCH_HEAD
  cd ..
fi

cd pulpcore
