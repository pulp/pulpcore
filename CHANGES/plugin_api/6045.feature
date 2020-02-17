A new method ``_reset_db_connection`` has been added to ``content.Handler``. It can be called before
accessing the db to ensure that the db connection is alive.
