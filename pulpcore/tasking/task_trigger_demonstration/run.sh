#!/bin/sh
set -e

psql -f "setup$1.sql"

psql -f insert_tasks.sql &
psql -f insert_tasks.sql &
psql -f insert_tasks.sql &
psql -f insert_tasks.sql &

wait
