#!/usr/bin/env python3
import os
import sys


def manage():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "pulpcore.app.settings")

    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    manage()
