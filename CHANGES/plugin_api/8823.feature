Added a ``timestamp_of_interest`` field to Content and Artifacts. This field can be updated by
calling a new method ``touch()`` on Artifacts and Content. Plugin writers should call this method
whenever they deal with Content or Artifacts. For example, this includes places where Content is
uploaded or added to Repository Versions. This will prevent Content and Artifacts from being cleaned
up when orphan cleanup becomes a non-blocking task in pulpcore 3.15.
