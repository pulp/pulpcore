#!/bin/bash

pip install twine

django-admin runserver 24817 >> ~/django_runserver.log 2>&1 &
sleep 5

cd /home/travis/build/pulp/pulpcore/
export REPORTED_VERSION=$(http :24817/pulp/api/v3/status/ | jq --arg plugin pulpcore -r '.versions[] | select(.component == $plugin) | .version')
export COMMIT_COUNT="$(git rev-list ${REPORTED_VERSION}^..HEAD | wc -l)"
export VERSION=${REPORTED_VERSION}.dev.${COMMIT_COUNT}

export response=$(curl --write-out %{http_code} --silent --output /dev/null https://pypi.org/project/pulpcore-client/$VERSION/)

if [ "$response" == "200" ];
then
    exit
fi

cd
git clone https://github.com/pulp/pulp-swagger-codegen.git
cd pulp-swagger-codegen

sudo ./generate.sh pulpcore python $VERSION
sudo chown -R travis:travis pulpcore-client
cd pulpcore-client
python setup.py sdist bdist_wheel --python-tag py3
twine upload dist/* -u pulp -p $PYPI_PASSWORD
exit $?
