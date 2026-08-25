Reduced the memory overhead of the Redis worker `waiting_tasks` metric by streaming reserved-resource records instead of loading full `Task` objects.
