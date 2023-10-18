def tasks_table(tasks, performance_task_name):
    """Return overview of tasks."""
    out = []
    for t in tasks:
        task_duration = t.finished_at - t.started_at
        waiting_time = t.started_at - t.pulp_created
        out.append(
            "\n-> {task_name} => Waiting time (s): {wait} | Service time (s): {service}".format(
                task_name=performance_task_name,
                wait=waiting_time.total_seconds(),
                service=task_duration.total_seconds(),
            )
        )
    return "\n".join(out)


def print_fmt_experiment_time(label, start, end):
    """Print formatted label and experiment time."""
    print("\n-> {} => Experiment time (s): {}".format(label, (end - start).total_seconds()))


def report_tasks_stats(performance_task_name, tasks):
    """Print out basic stats about received tasks."""
    print(tasks_table(tasks, performance_task_name))
