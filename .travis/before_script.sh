#!/usr/bin/env sh
set -v

mkdir -p ~/.config/pulp_smash
cp .travis/pulp-smash-config.json ~/.config/pulp_smash/settings.json

sudo mkdir -p /var/lib/pulp/tmp
sudo mkdir /etc/pulp/
sudo chown -R travis:travis /var/lib/pulp

if [ "$DB" = 'mariadb' ]; then
  mysql -e 'CREATE DATABASE pulp;'
  echo "DATABASES = {
      'default': {
          'ENGINE': 'django.db.backends.mysql',
          'NAME': 'pulp',
          'USER': 'root',
          'CONN_MAX_AGE': 0,
      },
  }" | sudo tee -a /etc/pulp/settings.py
else
  psql -U postgres -c 'CREATE USER pulp WITH SUPERUSER LOGIN;'
  psql -U postgres -c 'CREATE DATABASE pulp;'
  echo "DATABASES = {
      'default': {
          'ENGINE': 'django.db.backends.postgresql_psycopg2',
          'NAME': 'pulp',
          'USER': 'pulp',
          'CONN_MAX_AGE': 0,
      },
  }" | sudo tee -a /etc/pulp/settings.py
fi

echo "SECRET_KEY: \"$(cat /dev/urandom | tr -dc 'a-z0-9!@#$%^&*(\-_=+)' | head -c 50)\"" | sudo tee -a /etc/pulp/settings.py

# Run migrations.
export DJANGO_SETTINGS_MODULE=pulpcore.app.settings
export PULP_CONTENT_HOST=localhost:8080
pulp-manager migrate --noinput

if [ "$TEST" != 'docs' ]; then
  pulp-manager makemigrations file --noinput
  pulp-manager migrate --noinput
fi

pulp-manager reset-admin-password --password admin
