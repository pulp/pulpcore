Added a check to prevent the removal of remotes that are in use by repository versions. As of now,
only remotes that are either referenced by zero repository versions or there is redundancy for
remote artifacts can be deleted. Similarly, remotes attached to repositories' objects cannot be
deleted as well.
