#!/bin/bash

set -eu -o pipefail

BRANCH=$(git branch --show-current)

if ! [[ "${BRANCH}" =~ ^[0-9]+\.[0-9]+$ ]]
then
  echo ERROR: This is not a release branch!
  exit 1
fi

NEW_VERSION="$(bump2version --dry-run --list release | sed -ne 's/^new_version=//p')"
echo "Release ${NEW_VERSION}"

if ! [[ "${NEW_VERSION}" == "${BRANCH}"* ]]
then
  echo ERROR: Version does not match release branch
  exit 1
fi

towncrier build --yes --version "${NEW_VERSION}"
bump2version release --commit --message "Release {new_version}" --tag --tag-name "{new_version}" --tag-message "Release {new_version}" --allow-dirty
bump2version patch --commit

git push origin "${BRANCH}" "${NEW_VERSION}"
