# Diagnostics

There is a `TASK_DIAGNOSTICS` setting which, if enabled, allows users to request collection of a number
of performance diagnostics for tasks by submitting an `X-TASK-DIAGNOSTICS` header with their request.
This is intended primarily for developer use as  some of these diagnostics add significant
runtime/memory overhead. The header can be submitted using Pulp CLI with the `--header option`. For example:

```bash
pulp --header X-Task-Diagnostics:memory,pyinstrument rpm repository sync --name foo
Started background task /api/pulp/default/api/v3/tasks/0198a9c3-5a37-716e-900b-cbdf5399f64f/
.......Done.
```

Pulp CLI can also be used to retrieve the URLs for downloading the profiler data.

```bash
pulp task profile-artifact-urls --href /api/pulp/default/api/v3/tasks/0198a9c3-5a37-716e-900b-cbdf5399f64f/
{
  "memory_profile": "https://pulphostname/pulp/content/default/115341ffbc5c32b379142936bd85ab658a83209a0ab03f495d0448bf1f9ffee0/0198a9d6-0680-717c-bed8-c90863b93d5d?expires=1755199643&validate_token=fca7c13e6a93c63086324e42ae63a7ae58da362220c05ac0e1cfe64ce6fc52bd:b346f8fd6846ce8f6e942011e8292c89adc536a306e5c3ca31b8ec9bec894e32",
  "pyinstrument_profile": "https://pulphostname/pulp/content/default/115341ffbc5c32b379142936bd85ab658a83209a0ab03f495d0448bf1f9ffee0/0198a9d6-069a-78f5-8823-20c87d4de5b8?expires=1755199643&validate_token=f5e288c51cdc50961f62c96ff89b831cc80dbedde8b67f843ab42631f65cd3ae:b96e7c996e1cd59ab22d8b8abdc6f242677f21925729baee5a4dfed60c54ee8a"

}
```

Eventually these artifacts are removed automatically by orphan cleanup and are no longer accessible.

`TASK_DIAGNOSTICS` is disabled by default.

The following diagnostics are supported currently:

- memory:
   Logs the task's max resident set size in MB logged over time
- pyinstrument:
   Dumps an HTML report from the pyinstrument profiler, if installed
- memray:
   Dumps a profile which can be processed with `memray`, which shows which lines and functions were
   responsible for the most allocations at the time of peak RSS of the process


## Memory Logging

The resident set size (RSS) of the process is measured every 2 seconds and logged to a file.

You can plot this with gnuplot by:

1. Downloading the memory log artifact, and saving it to a file such as `memory.datum` in your current
   working directory

2. Enter the `gnuplot` interactive environment.

3. Paste these commands:

   ```
   set ylabel "Task Process Megabytes (MB)"
   set xlabel "Seconds since task start"
   plot "memory.datum" with lines
   ```

4. Open your png chart saved at memory.png

## Pyinstrument Profiling

If the `pyinstrument` package is installed, a runtime profile of the execution of the task will be
produced and written to a file.

When downloaded and opened in a browser, this profile will present an interactive tree showing how
much time is being spent in various functions relative to the total runtime of the task.

Enabling this profiler adds a bit of overhead (10-20%) to the runtime of the task, and also may leak
a bit of memory over time. This can be problematic for very long-running tasks. Behavior of the 
profiler (including sampling interval, directly proportional to memory overhead) can be adjusted 
by tweaking the code manually if required.

## Memray Profiling

If the `memray` package is installed, a runtime profile of the execution of the task will be
produced and written to a file.

When downloaded and processed using `memray` (see [memray docs]), you can view the details of which
lines and functions were responsible for the most memory allocations at the time of peak process RSS.

Enabling this profiler adds significant overhead (25-40%+) to the runtime of the task. Behavior of the
profiler can be adjusted by tweaking the code manually if required, however, enabling most of the
additional options (such as profiling native callstacks, or recording the memory callstacks of the entire
process instead of merely max RSS) also adds additional runtime overhead and makes the resulting files
larger.

While the [memray docs] are recommended reading to fully grasp the options available, a recommended
starting point is:

1. Downloading the memray dump artifact, and saving it to a file such as `memray.bin` in your current
   working directory

2. python3 -m memray tree memray.bin

[memray docs]: https://bloomberg.github.io/memray/getting_started.html
