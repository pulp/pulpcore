#!/usr/bin/env sh
set -v

# dev_requirements should not be needed for testing; don't install them to make sure
pip install -r test_requirements.txt

if [ "$TEST" = 'docs' ]; then
  pip3 install -r doc_requirements.txt
fi

# Run Ansible playbook
cd ../ansible-pulp
ansible-galaxy install -r requirements.yml

ansible-playbook --connection=local --inventory 127.0.0.1, playbook.yml --extra-vars \
  "pulp_python_interpreter=$VIRTUAL_ENV/bin/python, pulp_install_dir=$VIRTUAL_ENV \
  pulp_db_type=$DB"


cd ../pulpcore
