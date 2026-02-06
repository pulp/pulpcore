Allow use of Django 5 as well as Django 4. Note the following breaking changes if upgrading to
Django 5: storage configuration must use the new ``STORAGES`` format instead of
``DEFAULT_FILE_STORAGE``, Python >= 3.10 is required, and PostgreSQL >= 14 is required.
