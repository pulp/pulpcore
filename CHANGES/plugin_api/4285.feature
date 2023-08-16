Made the current domain a shared resource for all tasks even with domains disabled, so tasks can
hold off all other operations by taking an exclusive lock on the (default) domain.
