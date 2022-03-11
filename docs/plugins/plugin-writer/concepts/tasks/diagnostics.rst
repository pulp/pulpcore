Diagnostics
===========

When users enable task diagnostics using the ``TASK_DIAGNOSTICS`` setting, all tasks will write out
diagnostic information to data files in ``/var/tmp/pulp/<task_UUID>/`` directory.

Memory Analysis
---------------

The memory is written to a file such as
``var/tmp/pulp/3367e577-4b09-44b6-9069-4a06c367776a/memory.datum``.

You can plot this with gnuplot by changing into the directory with the files you want to see then:

1) Enter the ``gnuplot`` interactive environment.

2) Paste these commands::

    set terminal png size 1200,900 enhanced font "Arial, 10"
    set output "memory.png"
    set ylabel "Task Process Megabytes (MB)"
    set xlabel "Seconds since task start"
    plot "memory.datum" with lines

3) Open your png chart saved at memory.png
