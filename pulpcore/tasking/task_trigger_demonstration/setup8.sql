-- Use xact advisory locks and serialize tasks by resources only.
-- Works and in theory should be much faster than global advisory lock.
-- Chosen solution.

DROP TABLE IF EXISTS task;

CREATE TABLE task (
  name text,
  sleep float,
  resources text[],
  created timestamptz unique  -- not null...
);

CREATE OR REPLACE FUNCTION on_insert_timestamp_task()
  RETURNS TRIGGER
  LANGUAGE plpgsql
  AS $$
    BEGIN
      PERFORM pg_advisory_xact_lock(4711, q.id) FROM (SELECT hashtext(res) AS id FROM unnest(NEW.resources) AS res ORDER BY id) AS q;
      NEW.created = clock_timestamp();

      -- Open the window for races.
      PERFORM pg_sleep(NEW.sleep);

      IF NEW.created <= (SELECT MAX(created) FROM task WHERE NEW.resources && task.resources)
      THEN
        RAISE EXCEPTION 'Clock screw detected.';
      END IF;
      IF NEW.created <= (SELECT MAX(created) FROM task)
      THEN
        RAISE NOTICE 'Uncritical clock screw detected.';
      END IF;
      RETURN NEW;
    END;
  $$
;

CREATE OR REPLACE TRIGGER on_insert_timestamp_task_trigger
  BEFORE INSERT
  ON task
  FOR EACH ROW
  EXECUTE FUNCTION on_insert_timestamp_task()
;
