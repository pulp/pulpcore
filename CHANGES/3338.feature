Allow labelling Content in pulp.

This adds `pulp_labels` to Content subclasses, using the same entities as used for
labelling Repositories, Remotes, and Distributions currently (q.v.). Labels can be added
when uploading Content, searched on using the `pulp_labels_select` filter to the list
endpoints, and set/unset on existing Content.
