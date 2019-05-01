#!/bin/bash

pip install twine

django-admin runserver 24817 >> ~/django_runserver.log 2>&1 &
sleep 5

cd /home/travis/build/pulp/pulpcore/
COMMIT_SHA="$(git rev-parse HEAD | cut -c1-8)"
export COMMIT_SHA

cd
git clone https://github.com/pulp/pulp-swagger-codegen.git
cd pulp-swagger-codegen

sudo ./generate.sh pulpcore python $COMMIT_SHA
sudo chown -R travis:travis pulpcore-client
cd pulpcore-client
python setup.py sdist bdist_wheel --python-tag py3
twine upload dist/* -u pulp -p $PYPI_PASSWORD
exit $?
