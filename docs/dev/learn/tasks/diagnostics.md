# Diagnostics

There is a `TASK_DIAGNOSTICS` setting which, if enabled, provides automatic collection of a number
of performance diagnostics for all executed tasks. This is intended primarily for developer use as
some of these diagnostics add significant runtime/memory overhead and therefore should not be
enabled in production environments (at last not without careful supervision).

`TASK_DIAGNOSTICS` is disabled by default.

The following diagnostics are supported currently:

- memory:
   Logs the task's max resident set size in MB logged over time
- pyinstrument:
   Dumps an HTML report from the pyinstrument profiler, if installed

When enabled, these are accessed by using HTTP GET requests to the path `${TASK_HREF}profile_artifacts/`
for the task which is under inspection. The response will contain a set of keys and corresponding URLs
which provides access to download the artifacts. Eventually these artifacts are removed automatically
by orphan cleanup and are no longer accessible.

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
automatically produced and written to a file.

When downloaded and opened in a browser, this profile will present an interactive tree showing how
much time is being spent in various functions relative to the total runtime of the task.

Enabling this profiler adds a bit of overhead (10-20%) to the runtime of the task, and also may leak
a bit of memory over time. This can be problematic for very long-running tasks. Behavior of the 
profiler (including sampling interval, directly proportional to memory overhead) can be adjusted 
by tweaking the code manually if required.
