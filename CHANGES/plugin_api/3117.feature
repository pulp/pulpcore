Created a wrapper type for UUID generation so that the implementation can potentially be
switched in the future.  UUIDs are just 128-bit integers - as long as they don't overlap
there is no explicit need to stick with any particular implementation. Plugin writers may
notice a migration created due to this change depending on how they have written the
plugin.
