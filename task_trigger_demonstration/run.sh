#!/bin/sh

## run 'psql -f setup<i>.sql' first

psql -f insert_tasks2.sql &
psql -f insert_tasks2.sql &
psql -f insert_tasks2.sql &
psql -f insert_tasks2.sql &

wait
