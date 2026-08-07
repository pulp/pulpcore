Added optional `added_between` and `removed_between` filters to the content list endpoints. Each
takes two repository versions (by HREF/PRN) as `base,target` and returns the net set of content
added or removed going from the base version to the target version, allowing diffs between two
arbitrary (possibly non-adjacent) repository versions instead of only the single-step difference
against the immediate predecessor.
