from asgiref.sync import sync_to_async


# This is useful for querysets which don't have async support yet. Django querysets issue a db call
# when the iterator for them is requested, so we need that to be wrapped in `sync_to_async` also.
iter_async = sync_to_async(iter)


@sync_to_async
def next_async(it):
    try:
        return next(it)
    except StopIteration:
        raise StopAsyncIteration


def sync_to_async_iterable(sync_iterable):
    """
    Creates an async iterable.

    The returned iterator is able to be reused and iterated through multiple times.

    Args:
        sync_iterable: An iterable to be asynchronously iterated through.
    """

    class _Wrapper:
        def __aiter__(self):
            self.sync_iterator = None
            return self

        async def __anext__(self):
            if self.sync_iterator is None:
                self.sync_iterator = await iter_async(sync_iterable)
            return await next_async(self.sync_iterator)

    return _Wrapper()
