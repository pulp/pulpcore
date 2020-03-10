#!/usr/bin/env bash
set -mveuo pipefail

export PULP_FILE_PR_NUMBER=$(echo $COMMIT_MSG | grep -oP 'Required\ PR:\ https\:\/\/github\.com\/pulp\/pulp_file\/pull\/(\d+)' | awk -F'/' '{print $7}')
export PULP_CERTGUARD_PR_NUMBER=$(echo $COMMIT_MSG | grep -oP 'Required\ PR:\ https\:\/\/github\.com\/pulp\/pulp-certguard\/pull\/(\d+)' | awk -F'/' '{print $7}')

pip install yq
PULP_FILE_BRANCH=$(yq -r ".additional_plugins | .[] | select(.name == \"pulp_file\") | .branch" template_config.yml)
echo PULP_FILE_BRANCH="$PULP_FILE_BRANCH"

cd ..
git clone https://github.com/pulp/pulp_file.git --branch "$PULP_FILE_BRANCH"
if [ -n "$PULP_FILE_PR_NUMBER" ]; then
  cd pulp_file
  git fetch --depth=1 origin pull/$PULP_FILE_PR_NUMBER/head:$PULP_FILE_PR_NUMBER
  git checkout $PULP_FILE_PR_NUMBER
  cd ..
fi

git clone --depth=1 https://github.com/pulp/pulp-certguard.git
if [ -n "$PULP_CERTGUARD_PR_NUMBER" ]; then
  cd pulp-certguard
  git fetch --depth=1 origin pull/$PULP_CERTGUARD_PR_NUMBER/head:$PULP_CERTGUARD_PR_NUMBER
  git checkout $PULP_CERTGUARD_PR_NUMBER
  cd ..
fi

cd pulpcore

if [[ "$TEST" == 's3' ]]; then
  export MINIO_ACCESS_KEY=AKIAIT2Z5TDYPX3ARJBA
  export MINIO_SECRET_KEY=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
  docker run -d -p 0.0.0.0:9000:9000 -e MINIO_ACCESS_KEY=$MINIO_ACCESS_KEY -e MINIO_SECRET_KEY=$MINIO_SECRET_KEY minio/minio server /data
  wget https://dl.min.io/client/mc/release/linux-amd64/mc
  chmod +x mc
  sudo mv mc /usr/local/bin
fi
