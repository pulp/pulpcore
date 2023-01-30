import backoff


def dummy_task():
    """Dummy task, that can be used in tests."""
    pass


@backoff.on_exception(backoff.expo, BaseException)
def gooey_task(interval):
    """A sleep task that tries to avoid being killed by ignoring all exceptions."""
    from time import sleep

    sleep(interval)
