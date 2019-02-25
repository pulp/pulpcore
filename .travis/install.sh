#!/usr/bin/env sh
set -v

# dev_requirements should not be needed for testing; don't install them to make sure
pip install "Django<=$DJANGO_MAX"
pip install -r test_requirements.txt
pip install -e .

if [ "$TEST" = 'docs' ]; then
  pip3 install -r doc_requirements.txt
  return "$?"
fi

export COMMIT_MSG=$(git show HEAD^2 -s)
export PULP_FILE_PR_NUMBER=$(echo $COMMIT_MSG | grep -oP 'Required\ PR:\ https\:\/\/github\.com\/pulp\/pulp_file\/pull\/(\d+)' | awk -F'/' '{print $7}')
export PULP_SMASH_PR_NUMBER=$(echo $COMMIT_MSG | grep -oP 'Required\ PR:\ https\:\/\/github\.com\/PulpQE\/pulp-smash\/pull\/(\d+)' | awk -F'/' '{print $7}')
export PULP_PLUGIN_PR_NUMBER=$(echo $COMMIT_MSG | grep -oP 'Required\ PR:\ https\:\/\/github\.com\/pulp\/pulpcore-plugin\/pull\/(\d+)' | awk -F'/' '{print $7}')

if [ -z "$PULP_PLUGIN_PR_NUMBER" ]; then
  pip install git+https://github.com/pulp/pulpcore-plugin.git
else
  cd ../
  git clone https://github.com/pulp/pulpcore-plugin.git
  cd pulpcore-plugin
  git fetch origin +refs/pull/$PULP_PLUGIN_PR_NUMBER/merge
  git checkout FETCH_HEAD
  pip install -e .
  cd ../pulpcore
fi

if [ -z "$PULP_FILE_PR_NUMBER" ]; then
  pip install git+https://github.com/pulp/pulp_file.git#egg=pulp_file
else
  cd ../
  git clone https://github.com/pulp/pulp_file.git
  cd pulp_file
  git fetch origin +refs/pull/$PULP_FILE_PR_NUMBER/merge
  git checkout FETCH_HEAD
  pip install -e .
  cd ../pulpcore
fi

if [ ! -z "$PULP_SMASH_PR_NUMBER" ]; then
  pip uninstall -y pulp-smash
  cd ../
  git clone https://github.com/PulpQE/pulp-smash.git
  cd pulp-smash
  git fetch origin +refs/pull/$PULP_SMASH_PR_NUMBER/merge
  git checkout FETCH_HEAD
  pip install -e .
  cd ../pulpcore
fi
