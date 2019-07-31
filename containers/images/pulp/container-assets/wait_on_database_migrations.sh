#!/bin/bash

database_migrated=false

echo "Checking for database migrations"
while [ $database_migrated = false ]; do
  django-admin showmigrations | grep '\[ \]'
  if [ $? -gt 0 ]; then
    echo "Database migrated!"
    database_migrated=true
  else
    sleep 5
  fi
done

if [ $database_migrated = false ]; then
  echo "Database not migrated in time, exiting"
  exit 1
else
  exit 0
fi
