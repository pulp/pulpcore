Added network configuration fields (`total_timeout`, `connect_timeout`, `sock_connect_timeout`,
`sock_read_timeout`, `download_concurrency`, `max_retries`) to the Upstream Pulp model, allowing
these settings to be propagated to remotes created during replication.
