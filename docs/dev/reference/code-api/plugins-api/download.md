

# pulpcore.plugin.download

The module implements downloaders that solve many of the common problems plugin writers have while
downloading remote data. A high level list of features provided by these downloaders include:

- auto-configuration from remote settings (auth, ssl, proxy)
- synchronous or parallel downloading
- digest and size validation computed during download
- grouping downloads together to return to the user when all files are downloaded
- customizable download behaviors via subclassing

All classes documented here should be imported directly from the
`pulpcore.plugin.download` namespace.

## Basic Downloading

The most basic downloading from a url can be done like this:

```
downloader = HttpDownloader('http://example.com/')
result = downloader.fetch()
```

The example above downloads the data synchronously. The
`pulpcore.plugin.download.HttpDownloader.fetch` call blocks until the data is
downloaded and the `pulpcore.plugin.download.DownloadResult` is returned or a fatal
exception is raised.

## Parallel Downloading

Any downloader in the `pulpcore.plugin.download` package can be run in parallel with the
`asyncio` event loop. Each downloader has a
`pulpcore.plugin.download.BaseDownloader.run` method which returns a coroutine object
that `asyncio` can schedule in parallel. Consider this example:

```
download_coroutines = [
    HttpDownloader('http://example.com/').run(),
    HttpDownloader('http://pulpproject.org/').run(),
]

loop = asyncio.get_event_loop()
done, not_done = loop.run_until_complete(asyncio.wait([download_coroutines]))

for task in done:
    try:
        task.result()  # This is a DownloadResult
    except Exception as error:
        pass  # fatal exceptions are raised by result()
```



## Download Results

The download result contains all the information about a completed download and is returned from a
the downloader's `run()` method when the download is complete.

```{eval-rst}
.. autoclass:: pulpcore.plugin.download.DownloadResult
    :no-members:
```



## Configuring from a Remote

When fetching content during a sync, the remote has settings like SSL certs, SSL validation, basic
auth credentials, and proxy settings. Downloaders commonly want to use these settings while
downloading. The Remote's settings can automatically configure a downloader either to download a
`url` or a `pulpcore.plugin.models.RemoteArtifact` using the
`pulpcore.plugin.models.Remote.get_downloader` call. Here is an example download from a URL:

```
downloader = my_remote.get_downloader(url='http://example.com')
downloader.fetch()  # This downloader is configured with the remote's settings
```

Here is an example of a download configured from a RemoteArtifact, which also configures the
downloader with digest and size validation:

```
remote_artifact = RemoteArtifact.objects.get(...)
downloader = my_remote.get_downloader(remote_artifact=ra)
downloader.fetch()  # This downloader has the remote's settings and digest+validation checking
```

The `pulpcore.plugin.models.Remote.get_downloader` internally calls the
`DownloaderFactory`, so it expects a `url` that the `DownloaderFactory` can build a downloader for.
See the `pulpcore.plugin.download.DownloaderFactory` for more information on
supported urls.

!!! tip

    The `pulpcore.plugin.models.Remote.get_downloader` accepts kwargs that can
    enable size or digest based validation, and specifying a file-like object for the data to be
    written into. See `pulpcore.plugin.models.Remote.get_downloader` for more
    information.


!!! note

    All `pulpcore.plugin.download.HttpDownloader` downloaders produced by the same
    remote instance share an `aiohttp` session, which provides a connection pool, connection
    reusage and keep-alives shared across all downloaders produced by a single remote.




## Automatic Retry

The `pulpcore.plugin.download.HttpDownloader` will automatically retry 10 times if the
server responds with one of the following error codes:

- 429 - Too Many Requests



## Exception Handling

Unrecoverable errors of several types can be raised during downloading. One example is a
`validation exception <validation-exceptions>` that is raised if the content downloaded fails
size or digest validation. There can also be protocol specific errors such as an
`aiohttp.ClientResponse` being raised when a server responds with a 400+ response such as an HTTP
403\.

Plugin writers can choose to halt the entire task by allowing the exception be uncaught which
would mark the entire task as failed.

!!! note

    The `pulpcore.plugin.download.HttpDownloader` automatically retry in some cases, but if
    unsuccessful will raise an exception for any HTTP response code that is 400 or greater.




## Custom Download Behavior

Custom download behavior is provided by subclassing a downloader and providing a new `run()` method.
For example you could catch a specific error code like a 404 and try another mirror if your
downloader knew of several mirrors. Here is an [example of that](https://gist.github.com/bmbouter/bbacae99d3edfb145db1498e34fa6187#file-mirrorlist-py-L24-L75) in
code.

A custom downloader can be given as the downloader to use for a given protocol using the
`downloader_overrides` on the `pulpcore.plugin.download.DownloaderFactory`.
Additionally, you can implement the `pulpcore.plugin.models.Remote.get_downloader`
method to specify the `downloader_overrides` to the
`pulpcore.plugin.download.DownloaderFactory`.



## Adding New Protocol Support

To create a new protocol downloader implement a subclass of the
`pulpcore.plugin.download.BaseDownloader`. See the docs on
`pulpcore.plugin.download.BaseDownloader` for more information on the requirements.



## Download Factory

The DownloaderFactory constructs and configures a downloader for any given url. Specifically:

1. Select the appropriate downloader based from these supported schemes: `http`, `https` or `file`.
2. Auto-configure the selected downloader with settings from a remote including (auth, ssl,
   proxy).

The `pulpcore.plugin.download.DownloaderFactory.build` method constructs one
downloader for any given url.

!!! note
    Any `HttpDownloader <http-downloader>` objects produced by an instantiated
    `DownloaderFactory` share an `aiohttp` session, which provides a connection pool, connection
    reusage and keep-alives shared across all downloaders produced by a single factory.


!!! tip
    The `pulpcore.plugin.download.DownloaderFactory.build` method accepts kwargs that
    enable size or digest based validation or the specification of a file-like object for the data
    to be written into. See `pulpcore.plugin.download.DownloaderFactory.build` for
    more information.


```{eval-rst}
.. autoclass:: pulpcore.plugin.download.DownloaderFactory
    :members:
```



## HttpDownloader

This downloader is an asyncio-aware parallel downloader which is the default downloader produced by
the `downloader-factory` for urls starting with `http://` or `https://`. It also supports
synchronous downloading using `pulpcore.plugin.download.HttpDownloader.fetch`.

```{eval-rst}
.. autoclass:: pulpcore.plugin.download.HttpDownloader
    :members:
    :inherited-members: fetch
```



## FileDownloader

This downloader is an asyncio-aware parallel file reader which is the default downloader produced by
the `downloader-factory` for urls starting with `file://`.

```{eval-rst}
.. autoclass:: pulpcore.plugin.download.FileDownloader
    :members:
    :inherited-members: fetch
```



## BaseDownloader

This is an abstract downloader that is meant for subclassing. All downloaders are expected to be
descendants of BaseDownloader.

```{eval-rst}
.. autoclass:: pulpcore.plugin.download.BaseDownloader
    :members:

```



## Validation Exceptions

```{eval-rst}
.. autoclass:: pulpcore.exceptions.DigestValidationError
    :noindex:
```

```{eval-rst}
.. autoclass:: pulpcore.exceptions.SizeValidationError
    :noindex:
```

```{eval-rst}
.. autoclass:: pulpcore.exceptions.ValidationError
    :noindex:
```
