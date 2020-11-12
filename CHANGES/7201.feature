Exposed ``aiohttp.ClientTimeout`` fields in ``Remote`` as ``connect_timeout``,
``sock_connect_timeout``, ``sock_read_timeout``, and ``total_timeout``.

This replaces the previous hard-coded 600 second timeout for sock_connect and sock_read,
giving per-``Remote`` control of all four ``ClientTimeout`` fields to the user.
