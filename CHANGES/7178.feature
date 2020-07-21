Change the default deployment layout

This changes the default deployment layout. The main change is that MEDIA_ROOT gets its own
directory. This allows limiting the file permissions in a shared Pulp 2 + Pulp 3 deployment and the
SELinux file contexts. Another benefit is compatibility with django_extensions' unreferenced_files
command which lists all files in MEDIA_ROOT that are not in the database.

Other paths are kept on the same absolute paths. The documentation is updated to show the latest
best practices.
