#!/bin/bash

git clone https://github.com/PulpQE/pulp-fixtures.git
cd pulp-fixtures
make all
cp -R fixtures /var/www/html
sudo service nginx restart
