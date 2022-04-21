from gettext import gettext as _

from django.core.management import BaseCommand


class Command(BaseCommand):
    """
    Django management command for printing a summary report of a Stages API pipeline run.
    """

    help = (
        "Print a summary of a Stages API pipeline run. This command is provided as a tech "
        "preview and may not work properly or change in the future."
    )

    def add_arguments(self, parser):
        parser.add_argument("file_path", help=_("The path to the sqlite3 db with the run data."))

    def handle(self, *args, **options):
        import sqlite3

        CONN = sqlite3.connect(options["file_path"])
        c = CONN.cursor()

        c.execute("SELECT uuid, name, num FROM stages ORDER BY num ASC")

        stages = []
        stages_map = {}
        for row in c.fetchall():
            new_dict = {
                "uuid": row[0],
                "name": row[1],
                "waiting_time_sum": 0.0,
                "service_time_sum": 0.0,
                "length_sum": 0,
                "interarrival_time_sum": 0.0,
            }
            stages.append(new_dict)
            stages_map[row[0]] = new_dict

        c.execute("SELECT uuid, waiting_time, service_time FROM traffic")

        in_queue_count = 0
        for row in c.fetchall():
            in_queue_count = in_queue_count + 1
            stages_map[row[0]]["waiting_time_sum"] += row[1]
            stages_map[row[0]]["service_time_sum"] += row[2]

        c.execute("SELECT uuid, length, interarrival_time FROM system")

        arrival_count = 0
        for row in c.fetchall():
            arrival_count = arrival_count + 1
            stages_map[row[0]]["length_sum"] += row[1]
            stages_map[row[0]]["interarrival_time_sum"] += row[2]

        for stage in stages:
            msg = "{name}\n\tservice time average: {srv_avg:4f}\n"
            if in_queue_count == 0:
                # This is the first queue that gets no put() calls, so avoid DivisionByZero errors
                waiting_avg = srv_avg = length_avg = interarrival_avg = 0
            else:
                waiting_avg = stage["waiting_time_sum"] / in_queue_count
                srv_avg = stage["service_time_sum"] / in_queue_count
                length_avg = stage["length_sum"] / arrival_count
                interarrival_avg = stage["interarrival_time_sum"] / arrival_count

            print(
                "\n"
                "    |\n"
                "    |waiting time average: {wt:4f}\n"
                "    |queue length average: {ln:4f}\n"
                "    |interarrival average: {inter:4f}\n"
                "    |\n"
                "    \u030C\n".format(wt=waiting_avg, ln=length_avg, inter=interarrival_avg)
            )
            print(msg.format(name=stage["name"], srv_avg=srv_avg))
