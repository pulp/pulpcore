Exposed the `no_content_change_since` field on the Distribution API endpoint to return a timestamp
since when the distributed content served by a distribution has not changed. If the value equals to
`null`, no such a guarantee about the content change is given.
