Added artifact path overlap checks for repo versions and publications. Plugin writers should call
``validate_version_paths()`` or ``validate_publication_paths()`` during the finalize step when
creating RepositoryVersions or Publications (respectively).
