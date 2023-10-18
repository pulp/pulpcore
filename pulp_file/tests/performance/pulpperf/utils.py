import logging
import time
import requests


def measureit(func, *args, **kwargs):
    """Measure execution time of passed function."""
    logging.debug("Measuring duration of %s %s %s" % (func.__name__, args, kwargs))
    before = time.perf_counter()
    out = func(*args, **kwargs)
    after = time.perf_counter()
    return after - before, out


def parse_pulp_manifest(url):
    """Parse pulp manifest."""
    response = requests.get(url)
    response.text.split("\n")
    data = [i.strip().split(",") for i in response.text.split("\n")]
    return [(i[0], i[1], int(i[2])) for i in data if i != [""]]
