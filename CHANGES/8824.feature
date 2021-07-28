Changed orphan cleanup task to be a non-blocking task that can be run at any time. Added a
``ORPHAN_PROTECTION_TIME`` setting that can be configured for how long orphan Content and
Artifacts are kept before becoming candidates for deletion by the orphan cleanup task.
