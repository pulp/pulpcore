#!/usr/bin/env python

import os
import socket
import sys
import time

if __name__ == "__main__":

    postgres_is_alive = False
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tries = 0
    print("Waiting on postgresql to start...")
    while not postgres_is_alive and tries < 100:
        tries += 1
        try:
            print("Checking postgres host %s" % os.environ["POSTGRES_SERVICE_HOST"])
            s.connect((os.environ["POSTGRES_SERVICE_HOST"], 5432))
        except socket.error:
            time.sleep(3)
        else:
            postgres_is_alive = True

    if postgres_is_alive:
        print("Postgres started!")
        sys.exit(0)
    else:
        print("Unable to reach postgres on port 5432")
        sys.exit(1)
