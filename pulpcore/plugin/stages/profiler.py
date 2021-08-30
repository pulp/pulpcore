from asyncio import Queue
import pathlib
import time
import uuid

from pulpcore.app.models import Task


CONN = None


class ProfilingQueue(Queue):
    """
    A customized subclass of asyncio.Queue that records time in the queue and between queues.

    This Profiler records some data on items that are inserted and removed from Queues. This data is
    stored on items in a dictionary attribute called 'extra_data'. If this attribute does not exist
    on an item, the ProfileQueue adds it.

    The following statistics are computed for each Queue and the stage that it feeds into:

        * waiting time - The number of seconds an item waited in the Queue for this stage.
        * service time - The number of seconds an item received service in this stage.
        * queue_length - The number of waiting items in the queue, measured before each new arrival.
        * interarrival_time - The number of seconds since the previous arrival to this Queue.

    See the :meth:`create_profile_db_and_connection()` docs for more info on the database tables and
    layout.

    Args:
         stage_uuid (uuid.UUID): The uuid of the stage this ProfilingQueue delivers work into.
         args (tuple): unused positional arguments
         kwargs (dict): unused keyword arguments
    """

    def __init__(self, stage_uuid, *args, **kwargs):
        self.last_arrival_time = time.time()
        self.stage_uuid = stage_uuid
        return super().__init__(*args, **kwargs)

    def get_nowait(self):
        """
        Thinly wrap `asyncio.get_nowait` and record when get_nowait() operations happen.
        """
        item = super().get_nowait()
        if item:
            now = time.time()
            item.extra_data["last_waiting_time"] = now - item.extra_data["lastput_time"]
            item.extra_data["last_get_time"] = now
        return item

    def put_nowait(self, item):
        """
        Thinly wrap `asyncio.put_nowait` happens and write statistics about them to the sqlite3 DB.

        This method computes and writes the following statistics: waiting time, service time, queue
        length, and interarrival time.
        """
        if item:
            now = time.time()
            if not hasattr(item, "extra_data"):
                # track stages that use QuerySet items too
                item.extra_data = {}
            try:
                last_waiting_time = item.extra_data["last_waiting_time"]
            except KeyError:
                pass
            else:
                service_time = now - item.extra_data["last_get_time"]
                sql = (
                    "INSERT INTO traffic (uuid, waiting_time, service_time) VALUES ("
                    "'{uuid}','{waiting_time}','{service_time}')"
                )
                formatted_sql = sql.format(
                    uuid=self.stage_uuid, waiting_time=last_waiting_time, service_time=service_time
                )
                CONN.cursor().execute(formatted_sql)

            interarrival_time = now - self.last_arrival_time
            sql = (
                "INSERT INTO system (uuid, length, interarrival_time) VALUES ("
                "'{uuid}','{length}','{interarrival}')"
            )
            formatted_sql = sql.format(
                uuid=self.stage_uuid, length=super().qsize(), interarrival=interarrival_time
            )
            CONN.cursor().execute(formatted_sql)
            CONN.commit()

            item.extra_data["lastput_time"] = now
            self.last_arrival_time = now
        return super().put_nowait(item)

    @staticmethod
    def make_and_record_queue(stage, num, maxsize):
        """
        Create a ProfileQueue that is associated with the stage it feeds and record it in sqlite3.

        Args:
            stage (uuid.UUID): The uuid of this stage for correlation with other table data.
            num: (int): The number in the pipeline this stage is at, starting from 0, 1, etc.
            maxsize: The `maxsize` parameter being used to configure the ProfilingQueue with.

        Returns:
            ProfilingQueue: The configured ProfilingQueue that was also recorded in the db.
        """
        if CONN is None:
            create_profile_db_and_connection()
        stage_id = uuid.uuid4()
        stage_name = ".".join([stage.__class__.__module__, stage.__class__.__name__])
        sql = "INSERT INTO stages (uuid, name, num) VALUES ('{uuid}','{stage}','{num}')"
        formatted_sql = sql.format(uuid=stage_id, stage=stage_name, num=num)
        CONN.cursor().execute(formatted_sql)
        in_q = ProfilingQueue(stage_id, maxsize=maxsize)
        CONN.commit()
        return in_q


def create_profile_db_and_connection():
    """
    Create a profile db from this tasks UUID and a sqlite3 connection to that databases.

    The database produced has three tables with the following SQL format:

    The `stages` table stores info about the pipeline itself and stores 3 fields
    * uuid - the uuid of the stage
    * name - the name of the stage
    * num - the number of the stage starting at 0

    The `traffic` table stores 3 fields:
    * uuid - the uuid of the stage this queue feeds into
    * waiting_time - the amount of time the item is waiting in the queue before it enters the stage.
    * service_time - the service time the item spent in the stage.

    The `system` table stores 3 fields:
    * uuid - The uuid of stage this queue feeds into
    * length - The length of items in this queue, measured just before each arrival.
    * interarrival_time - The amount of time since the last arrival.
    """
    debug_data_dir = "/var/lib/pulp/debug/"
    pathlib.Path(debug_data_dir).mkdir(parents=True, exist_ok=True)
    current_task = Task.current()
    if current_task:
        db_path = debug_data_dir + str(current_task.pk)
    else:
        db_path = debug_data_dir + str(uuid.uuid4())

    import sqlite3

    global CONN
    CONN = sqlite3.connect(db_path)
    c = CONN.cursor()

    # Create table
    c.execute(
        """CREATE TABLE stages
                 (uuid varchar(36), name text, num int)"""
    )

    # Create table
    c.execute(
        """CREATE TABLE traffic
                 (uuid varchar(36), waiting_time real, service_time real)"""
    )

    # Create table
    c.execute(
        """CREATE TABLE system
                 (uuid varchar(36), length int, interarrival_time real)"""
    )

    return CONN
