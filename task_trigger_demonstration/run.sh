#!/bin/sh

## run 'psql -f setup<i>.sql' first

psql -f insert_tasks.sql &
psql -f insert_tasks.sql &
psql -f insert_tasks.sql &
psql -f insert_tasks.sql &

wait
