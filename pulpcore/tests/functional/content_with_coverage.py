import atexit
import sys
import coverage

cov = coverage.Coverage()
cov.start()


def finalize_coverage():
    print("writing coverage", file=sys.stderr)
    cov.stop()
    cov.save()


atexit.register(finalize_coverage)

from ...content import server  # noqa
