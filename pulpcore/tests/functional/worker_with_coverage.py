import sys
import coverage

from pulpcore.tasking.worker import PulpWorker


class CoveragePulpWorker(PulpWorker):
    def perform_job(self, job, queue):
        cov = coverage.Coverage()
        cov.start()

        super().perform_job(job, queue)

        print('writing coverage', file=sys.stderr)
        cov.stop()
        cov.save()
