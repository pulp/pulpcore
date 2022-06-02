Added new access condition ``has_required_repo_perms_on_upload`` for RBAC plugins to use to require
users to specify a repository when uploading content. If not used when uploading content, non-admin
users will not be able to see their uploaded content if queryset scoping is enabled.
