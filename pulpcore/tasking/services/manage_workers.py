"""
This module manages creation, deletion, starting, and stopping of the systemd unit files for Pulp's
RQ workers. It accepts one parameter, which must be start or stop.
"""
import multiprocessing
import os
import subprocess
import sys
from glob import glob

_ENVIRONMENT_FILE = os.path.join("/", "etc", "default", "pulp-workers")
_SYSTEMD_UNIT_PATH = os.path.join("/", "run", "systemd", "system")
_UNIT_FILENAME_TEMPLATE = "pulpcore-worker-%s.service"
_WORKER_TEMPLATE = """[Unit]
Description=Pulp Worker #%(num)s
After=network.target

[Service]
EnvironmentFile=%(environment_file)s
User=apache
WorkingDirectory=/var/run/pulp/
ExecStart=rq worker -n reserved-resource-worker-%(num)s@%%%%h\
          -w pulpcore.tasking.worker.PulpWorker
          --pid=/var/run/pulp/reserved-resource-worker-%(num)s.pid
KillSignal=SIGQUIT
"""


def _get_concurrency():
    """
    Process the _ENVIRONMENT_FILE to see if the user has specified a desired
    concurrency setting there. If they have, return that value. Otherwise, return the number of
    processors detected.

    Returns:
        int: The number of workers that should be running
    """
    pipe = subprocess.Popen(
        ". %s; echo $PULP_CONCURRENCY" % _ENVIRONMENT_FILE, stdout=subprocess.PIPE, shell=True
    )
    output = pipe.communicate()[0].strip()
    if output:
        return int(output)
    return multiprocessing.cpu_count()


def _get_file_contents(path):
    """
    Open the file at path, read() it, close the file, and return a string of its contents.

    Args:
        path (str): The path to the file

    Returns:
        str: The file's contents
    """
    with open(path) as f:
        return f.read()


def _start_workers():
    """
    Build unit files to represent the workers, if they aren't already defined, and call systemctl to
    start them.
    """
    concurrency = _get_concurrency()
    for i in range(concurrency):
        unit_filename = _UNIT_FILENAME_TEMPLATE % i
        unit_path = os.path.join(_SYSTEMD_UNIT_PATH, unit_filename)
        unit_contents = _WORKER_TEMPLATE % {"num": i, "environment_file": _ENVIRONMENT_FILE}
        if not os.path.exists(unit_path) or _get_file_contents(unit_path) != unit_contents:
            with open(unit_path, "w") as unit_file:
                unit_file.write(unit_contents)
        # Start the worker
        pipe = subprocess.Popen(
            "systemctl start %s" % unit_filename,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=True,
        )
        stdout, stderr = pipe.communicate()
        print(stdout)
        if pipe.returncode != 0:
            sys.stderr.write(str(stderr))
            sys.exit(pipe.returncode)


def _stop_workers():
    """
    Stop all the workers that have unit files at _SYSTEMD_UNIT_PATH.
    """
    glob_path = os.path.join(_SYSTEMD_UNIT_PATH, _UNIT_FILENAME_TEMPLATE % "*")
    pipes = []
    for worker in glob(glob_path):
        pipes.append(
            subprocess.Popen(
                "systemctl stop %s" % os.path.basename(worker),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=True,
            )
        )
    exit_code = os.EX_OK
    for pipe in pipes:
        stdout, stderr = pipe.communicate()
        if stdout:
            print(stdout)
        if stderr:
            sys.stderr.write(str(stderr))
        if pipe.returncode != os.EX_OK:
            # This is arbitrary, but we're going to pick the exit code of the last worker that
            # failed for our process to return.
            exit_code = pipe.returncode
    if exit_code != os.EX_OK:
        sys.exit(exit_code)


def main():
    """
    This function is executed by the systemd unit file to manage the worker units.
    """
    if len(sys.argv) != 2 or sys.argv[1] not in ("start", "stop"):
        sys.stderr.write('This script may only be called with "start" or "stop" as an argument.\n')
        sys.exit(1)
    _action = sys.argv[1]

    if _action == "start":
        _start_workers()
    elif _action == "stop":
        _stop_workers()


if __name__ == "__main__":
    main()  # nocover
