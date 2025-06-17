-- xact advisory lock on statement trigger.
-- Works but  still rather slow.

DROP TABLE IF EXISTS task;

CREATE TABLE task (
  name text,
  sleep float,
  resources text[],
  created timestamptz unique  -- not null...
);

CREATE OR REPLACE FUNCTION on_insert_timestamp_task_lock()
  RETURNS TRIGGER
  LANGUAGE plpgsql
  AS $$
    BEGIN
      PERFORM pg_advisory_xact_lock(4711);
      RETURN NULL;
    END;
  $$
;

CREATE OR REPLACE FUNCTION on_insert_timestamp_task()
  RETURNS TRIGGER
  LANGUAGE plpgsql
  AS $$
    BEGIN
      NEW.created = clock_timestamp();

      -- Open the window for races.
      PERFORM pg_sleep(NEW.sleep);

      IF NEW.created <= (SELECT MAX(created) FROM task)
      THEN
        RAISE EXCEPTION 'Clock screw detected.';
      END IF;
      RETURN NEW;
    END;
  $$
;

CREATE OR REPLACE TRIGGER on_insert_timestamp_task_lock_trigger
  BEFORE INSERT
  ON task
  FOR EACH STATEMENT
  EXECUTE FUNCTION on_insert_timestamp_task_lock()
;

CREATE OR REPLACE TRIGGER on_insert_timestamp_task_trigger
  BEFORE INSERT
  ON task
  FOR EACH ROW
  WHEN (NEW.created is null)
  EXECUTE FUNCTION on_insert_timestamp_task()
;
