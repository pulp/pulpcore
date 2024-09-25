Added a formal "immediate" type of Task and changed workers behavior to prioritize those.
This labeling is exlusive to plugin code and should only be applied where it's known that
the task will finish shortly, like in updates of repositories, remotes, and distributions.
