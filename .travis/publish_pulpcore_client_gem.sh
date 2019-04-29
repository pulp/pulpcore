#!/bin/bash

openssl aes-256-cbc -K $encrypted_7ccb8decfcc9_key -iv $encrypted_7ccb8decfcc9_iv -in .travis/credentials.enc -out ~/.gem/credentials -d
sudo chmod 600 ~/.gem/credentials

django-admin runserver 24817 >> ~/django_runserver.log 2>&1 &
sleep 5

cd /home/travis/build/pulp/pulpcore/
COMMIT_SHA="$(git rev-parse HEAD | cut -c1-8)"
export COMMIT_SHA

cd

git clone https://github.com/pulp/pulp-swagger-codegen.git
cd pulp-swagger-codegen


sudo ./generate.sh pulpcore ruby $COMMIT_SHA
sudo chown travis:travis pulpcore-client
cd pulpcore-client
gem build pulpcore_client
GEM_FILE="$(ls | grep pulpcore_client-)"
gem push ${GEM_FILE}
