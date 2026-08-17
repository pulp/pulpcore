"""
Check `Plugin Writer's Guide`_ for more details.

Plugin Writer's Guide:
https://pulpproject.org/pulpcore/docs/dev/learn/plugin-concepts/
"""

from django.contrib.postgres.fields import HStoreField
from django.db import models

from pulpcore.app.models import AutoAddObjPermsMixin, BaseModel
from pulpcore.app.util import get_domain_pk


class ContentView(BaseModel, AutoAddObjPermsMixin):
    """
    A named, persistable scope composed of Distributions, searchable across domains.

    A ContentView lets API clients search across the content served by many Distributions --
    which may span domains other than the ContentView's own -- without passing raw lists of
    repository version hrefs on every request, and without bypassing Pulp's RBAC by querying
    the database directly. Each linked Distribution already carries version-tracking semantics
    (it can point to a Repository to track its latest version, a pinned RepositoryVersion, or a
    Publication), so the ContentView itself only needs to store *which* Distributions are in
    scope; resolving them to concrete RepositoryVersions happens at query time.

    Fields:
        name (models.TextField): The content view's name, unique within its domain.
        description (models.TextField): Optional human-readable description.
        pulp_labels (HStoreField): Dictionary of string values.

    Relations:
        pulp_domain (models.ForeignKey): The domain this ContentView is stored in. Standard
            domain-scoped resource: read/update/delete is governed by RBAC on the ContentView
            itself, same as any other Pulp resource.
        distributions (models.ManyToManyField): Distributions this ContentView searches across.
            These may belong to any domain the referencing user has read access to at the time
            they are added -- not just the ContentView's own domain -- which is what makes
            cross-domain search possible.
    """

    name = models.TextField(db_index=True)
    description = models.TextField(null=True)
    pulp_labels = HStoreField(default=dict)
    pulp_domain = models.ForeignKey("Domain", default=get_domain_pk, on_delete=models.PROTECT)
    distributions = models.ManyToManyField("Distribution", related_name="content_views")

    class Meta:
        unique_together = ("name", "pulp_domain")
        permissions = [
            ("manage_roles_contentview", "Can manage role assignments on content view"),
        ]
