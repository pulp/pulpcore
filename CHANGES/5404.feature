Enable users to gradually upgrade from `DEFAULT_FILE_STORAGE` and `STATIC_FILE_STORAGE` to 'STORAGES'.
These legacy settings were deprecated in Django 4.2 and will be removed in Pulp 3.85.

The [django-upgrade](https://github.com/adamchainz/django-upgrade?tab=readme-ov-file#django-42)
tool can be used to automatically upgrade the settings to the new form.
