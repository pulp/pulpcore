#!/usr/bin/env sh
set -v

COMMIT_MSG=$(git show HEAD^2 -s)
export COMMIT_MSG
export PULP_FILE_PR_NUMBER=$(echo $COMMIT_MSG | grep -oP 'Required\ PR:\ https\:\/\/github\.com\/pulp\/pulp_file\/pull\/(\d+)' | awk -F'/' '{print $7}')
export PULP_SMASH_PR_NUMBER=$(echo $COMMIT_MSG | grep -oP 'Required\ PR:\ https\:\/\/github\.com\/PulpQE\/pulp-smash\/pull\/(\d+)' | awk -F'/' '{print $7}')
export PULP_PLUGIN_PR_NUMBER=$(echo $COMMIT_MSG | grep -oP 'Required\ PR:\ https\:\/\/github\.com\/pulp\/pulpcore-plugin\/pull\/(\d+)' | awk -F'/' '{print $7}')
export PULP_ROLES_PR_NUMBER=$(echo $COMMIT_MSG | grep -oP 'Required\ PR:\ https\:\/\/github\.com\/pulp\/ansible-pulp\/pull\/(\d+)' | awk -F'/' '{print $7}')

cd ..
git clone https://github.com/pulp/ansible-pulp.git
if [ -n "$PULP_ROLES_PR_NUMBER" ]; then
  cd ansible-pulp
  git fetch origin +refs/pull/$PULP_ROLES_PR_NUMBER/merge
  git checkout FETCH_HEAD
  cd ..
fi

git clone https://github.com/pulp/pulpcore-plugin.git
if [ -n "$PULP_PLUGIN_PR_NUMBER" ]; then
  cd pulpcore-plugin
  git fetch origin +refs/pull/$PULP_PLUGIN_PR_NUMBER/merge
  git checkout FETCH_HEAD
  cd ..
fi

git clone https://github.com/pulp/pulp_file.git
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

if [ -n "$PULP_SMASH_PR_NUMBER" ]; then
  pip uninstall -y pulp-smash
  git clone https://github.com/PulpQE/pulp-smash.git
  cd pulp-smash
  git fetch origin +refs/pull/$PULP_SMASH_PR_NUMBER/merge
  git checkout FETCH_HEAD
  pip install -e .
  cd ..
fi


if [ "$DB" = 'mariadb' ]; then
  mysql -e 'CREATE DATABASE pulp;'
else
  psql -c 'CREATE DATABASE pulp OWNER travis;'
fi

pip install ansible
cp pulpcore/.travis/playbook.yml ansible-pulp/playbook.yml
cp pulpcore/.travis/postgres.yml ansible-pulp/postgres.yml
cp pulpcore/.travis/mariadb.yml ansible-pulp/mariadb.yml

cd pulpcore
