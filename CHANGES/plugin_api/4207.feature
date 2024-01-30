Added new ``reverse`` method that handles Pulp specific url formatting. Plugins should update
instances of ``django.urls.reverse`` and ``rest_framework.reverse`` to this new Pulp one.
