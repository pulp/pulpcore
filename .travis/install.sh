#!/usr/bin/env sh
set -v

# dev_requirements should not be needed for testing; don't install them to make sure
pip install -r test_requirements.txt

if [ "$TEST" = 'docs' ]; then
  pip3 install -r doc_requirements.txt
fi

# Run Ansible playbook
cd ../ansible-pulp3
ansible-galaxy install -r requirements.yml
ansible-playbook --connection=local --inventory 127.0.0.1, playbook.yml --extra-vars "pulp_python_interpreter=$VIRTUAL_ENV/bin/python, pulp_install_dir=$VIRTUAL_ENV"

# false for both postgresql and maria
# pulp_install_postgresql: false
# pulp_install_maria: false
    pulp_postgresql_user: 'travis'
cd ../pulpcore
