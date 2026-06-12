Added sync optimization that skips re-syncing when the remote manifest has not changed. An `optimize` flag on the sync endpoint (default `True`) allows forcing a full sync when needed.
