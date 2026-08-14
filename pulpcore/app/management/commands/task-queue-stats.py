"""
Report task queue wait statistics from `unblocked_at` / `started_at`.

Worker-queue wait is `started_at - unblocked_at`: the task was ready to run
(resources free) but no worker had picked it up yet. Resource wait is
`unblocked_at - pulp_created`.

Only meaningful for `WORKER_TYPE=pulpcore`. Redis workers do not use the
unblock mechanism, so those fields are not a reliable congestion signal there.
"""

import json
from datetime import timedelta
from gettext import gettext as _

from django.conf import settings
from django.core.management import BaseCommand
from django.db.models import F, FloatField, Func
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from pulpcore.app.models import AppStatus, Task
from pulpcore.constants import TASK_STATES


class EpochSeconds(Func):
    """PostgreSQL `EXTRACT(EPOCH FROM …)` as a float (subsecond precision)."""

    function = "EXTRACT"
    template = "%(function)s(EPOCH FROM %(expressions)s)"
    output_field = FloatField()


def _percentile(sorted_values, pct):
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return sorted_values[0]
    idx = min(len(sorted_values) - 1, max(0, round(pct / 100 * (len(sorted_values) - 1))))
    return sorted_values[idx]


def _fmt_seconds(value):
    if value is None:
        return "n/a"
    return f"{value:.3f}s"


def _summarize(values):
    if not values:
        return {"n": 0, "mean": None, "p50": None, "p90": None, "p99": None, "max": None}
    return {
        "n": len(values),
        "mean": sum(values) / len(values),
        "p50": _percentile(values, 50),
        "p90": _percentile(values, 90),
        "p99": _percentile(values, 99),
        "max": values[-1],
    }


class Command(BaseCommand):
    help = _("Summarize how long completed tasks waited for a worker after becoming unblocked.")

    def add_arguments(self, parser):
        parser.add_argument(
            "--hours",
            type=float,
            default=None,
            help=_("Only include tasks created in the last N hours."),
        )
        parser.add_argument(
            "--since",
            type=str,
            default=None,
            help=_("Only include tasks created at or after this ISO-8601 timestamp."),
        )
        parser.add_argument(
            "--top",
            type=int,
            default=15,
            help=_("Show the N task names with the highest mean worker wait (default: 15)."),
        )
        parser.add_argument(
            "--min-worker-wait",
            type=float,
            default=0.0,
            help=_("Only include tasks whose worker wait is at least this many seconds."),
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help=_("Emit machine-readable JSON instead of a text report."),
        )

    def handle(self, *args, **options):
        worker_type = getattr(settings, "WORKER_TYPE", "pulpcore")
        online_workers = AppStatus.objects.online().filter(app_type="worker").count()

        qs = Task.objects.filter(
            state=TASK_STATES.COMPLETED,
            unblocked_at__isnull=False,
            started_at__isnull=False,
            finished_at__isnull=False,
        )

        since = None
        if options["since"]:
            since = parse_datetime(options["since"])
            if since is None:
                self.stderr.write(self.style.ERROR(f"Invalid --since value: {options['since']}"))
                return
            if timezone.is_naive(since):
                since = timezone.make_aware(since, timezone.get_current_timezone())
        elif options["hours"] is not None:
            since = timezone.now() - timedelta(hours=options["hours"])

        if since is not None:
            qs = qs.filter(pulp_created__gte=since)

        qs = qs.annotate(
            worker_wait=EpochSeconds(F("started_at") - F("unblocked_at")),
            resource_wait=EpochSeconds(F("unblocked_at") - F("pulp_created")),
            total_wait=EpochSeconds(F("started_at") - F("pulp_created")),
            runtime=EpochSeconds(F("finished_at") - F("started_at")),
        )

        min_wait = options["min_worker_wait"]
        if min_wait:
            qs = qs.filter(worker_wait__gte=min_wait)

        rows = list(qs.values_list("name", "worker_wait", "resource_wait", "total_wait", "runtime"))

        worker_waits = sorted(r[1] for r in rows)
        resource_waits = sorted(r[2] for r in rows)
        total_waits = sorted(r[3] for r in rows)
        runtimes = sorted(r[4] for r in rows)

        by_name = {}
        for name, worker_wait, resource_wait, total_wait, runtime in rows:
            bucket = by_name.setdefault(
                name, {"worker": [], "resource": [], "total": [], "runtime": []}
            )
            bucket["worker"].append(worker_wait)
            bucket["resource"].append(resource_wait)
            bucket["total"].append(total_wait)
            bucket["runtime"].append(runtime)

        top_n = options["top"]
        top_names = sorted(
            (
                {
                    "name": name,
                    "n": len(stats["worker"]),
                    "worker_wait": _summarize(sorted(stats["worker"])),
                    "resource_wait": _summarize(sorted(stats["resource"])),
                    "total_wait": _summarize(sorted(stats["total"])),
                    "runtime": _summarize(sorted(stats["runtime"])),
                }
                for name, stats in by_name.items()
            ),
            key=lambda item: (
                item["worker_wait"]["mean"] if item["worker_wait"]["mean"] is not None else -1,
                item["n"],
            ),
            reverse=True,
        )[:top_n]

        null_unblocked = Task.objects.filter(state=TASK_STATES.COMPLETED, unblocked_at__isnull=True)
        if since is not None:
            null_unblocked = null_unblocked.filter(pulp_created__gte=since)
        null_unblocked_count = null_unblocked.count()

        currently_waiting_unblocked = None
        currently_waiting_blocked = None
        if worker_type == "pulpcore":
            currently_waiting_unblocked = Task.objects.filter(
                state=TASK_STATES.WAITING, unblocked_at__isnull=False
            ).count()
            currently_waiting_blocked = Task.objects.filter(
                state=TASK_STATES.WAITING, unblocked_at__isnull=True
            ).count()

        report = {
            "worker_type": worker_type,
            "online_workers": online_workers,
            "since": since.isoformat() if since else None,
            "min_worker_wait": min_wait,
            "completed_with_null_unblocked_at": null_unblocked_count,
            "currently_waiting_unblocked": currently_waiting_unblocked,
            "currently_waiting_blocked": currently_waiting_blocked,
            "worker_wait": _summarize(worker_waits),
            "resource_wait": _summarize(resource_waits),
            "total_wait": _summarize(total_waits),
            "runtime": _summarize(runtimes),
            "top_by_mean_worker_wait": top_names,
            "notes": [],
        }

        if worker_type != "pulpcore":
            report["notes"].append(
                "WORKER_TYPE is not pulpcore; unblocked_at is not maintained by Redis workers, "
                "so worker_wait is not a reliable congestion signal."
            )
        if null_unblocked_count:
            report["notes"].append(
                f"{null_unblocked_count} completed task(s) have null unblocked_at "
                "(common under Redis workers)."
            )

        if options["json"]:
            self.stdout.write(json.dumps(report, indent=2, default=str))
            return

        self.stdout.write("Task queue wait stats")
        self.stdout.write(f"  worker_type: {worker_type}")
        self.stdout.write(f"  online_workers: {online_workers}")
        self.stdout.write(f"  since: {since.isoformat() if since else 'all completed tasks'}")
        if min_wait:
            self.stdout.write(f"  min_worker_wait filter: {min_wait}s")
        self.stdout.write(
            f"  currently waiting (unblocked/blocked): "
            f"{currently_waiting_unblocked}/{currently_waiting_blocked}"
        )
        self.stdout.write(f"  completed with null unblocked_at: {null_unblocked_count}")
        self.stdout.write("")

        def print_summary(label, summary):
            self.stdout.write(
                f"{label}: n={summary['n']} mean={_fmt_seconds(summary['mean'])} "
                f"p50={_fmt_seconds(summary['p50'])} p90={_fmt_seconds(summary['p90'])} "
                f"p99={_fmt_seconds(summary['p99'])} max={_fmt_seconds(summary['max'])}"
            )

        print_summary("WORKER_WAIT  (started_at - unblocked_at)", report["worker_wait"])
        print_summary("RESOURCE_WAIT(unblocked_at - pulp_created)", report["resource_wait"])
        print_summary("TOTAL_WAIT   (started_at - pulp_created)", report["total_wait"])
        print_summary("RUNTIME      (finished_at - started_at)", report["runtime"])

        if top_names:
            self.stdout.write("")
            self.stdout.write(f"Top {len(top_names)} task names by mean worker wait:")
            for item in top_names:
                ww = item["worker_wait"]
                short = item["name"].rsplit(".", 1)[-1]
                self.stdout.write(
                    f"  mean={_fmt_seconds(ww['mean']):>8} p90={_fmt_seconds(ww['p90']):>8} "
                    f"max={_fmt_seconds(ww['max']):>8} n={ww['n']:<5} {short} ({item['name']})"
                )

        for note in report["notes"]:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING(f"Note: {note}"))
