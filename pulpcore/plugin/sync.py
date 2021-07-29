from asgiref.sync import sync_to_async


iter_async = sync_to_async(iter)


@sync_to_async
def next_async(it):
    try:
        return next(it)
    except StopIteration:
        raise StopAsyncIteration


async def sync_to_async_iterable(sync_iterable):
    """
    Utility method which runs each iteration of a synchronous iterable in a threadpool. It also
    sets a threadlocal inside the thread so calls to AsyncToSync can escape it. The implementation
    relies on `asgiref.sync.sync_to_async`.  thread_sensitive parameter for sync_to_async defaults
    to True. This code will run in the same thread as any outer code. This is needed for
    underlying Python code that is not threadsafe (for example, code which handles database
    connections).

    Args:
        sync_iterable (iter): A synchronous iterable such as a QuerySet.
    """
    sync_iterator = await iter_async(sync_iterable)
    while True:
        try:
            yield await next_async(sync_iterator)
        except StopAsyncIteration:
            return
