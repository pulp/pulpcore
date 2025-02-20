"""
Check `Plugin Writer's Guide`_ for more details.

Plugin Writer's Guide:
https://pulpproject.org/pulpcore/docs/dev/learn/plugin-concepts/
"""

from django.db import models
from pulpcore.plugin.models import BaseModel, EncryptedTextField, AutoAddObjPermsMixin
from pulpcore.app.util import get_domain_pk


class UpstreamPulp(BaseModel, AutoAddObjPermsMixin):
    ALL = "all"
    LABELED = "labeled"
    NODELETE = "nodelete"
    POLICY_CHOICES = (
        (ALL, "Replicate manages ALL local objects within the domain."),
        (
            LABELED,
            "Replicate will only manage the objects created from a previous replication, unlabled local objects will be untouched.",  # noqa: E501
        ),
        (
            NODELETE,
            "Replicate will not delete any local object whether they were created by replication or not.",  # noqa: E501
        ),
    )

    name = models.TextField(db_index=True)
    pulp_domain = models.ForeignKey("Domain", default=get_domain_pk, on_delete=models.PROTECT)

    base_url = models.TextField()
    api_root = models.TextField(default="pulp")
    domain = models.TextField(null=True)

    ca_cert = models.TextField(null=True)
    client_cert = models.TextField(null=True)
    client_key = EncryptedTextField(null=True)
    tls_validation = models.BooleanField(default=True)

    username = EncryptedTextField(null=True)
    password = EncryptedTextField(null=True)

    q_select = models.TextField(null=True)
    policy = models.TextField(choices=POLICY_CHOICES, default=ALL)

    last_replication = models.DateTimeField(null=True)

    class Meta:
        unique_together = ("name", "pulp_domain")
        permissions = [
            ("replicate_upstreampulp", "Can start a replication task"),
            ("manage_roles_upstreampulp", "Can manage roles on upstream pulps"),
        ]

    def set_last_replication_timestamp(self, timestamp):
        self.last_replication = timestamp
        # enforce the update without changing pulp_last_updated
        self.save(update_fields=["last_replication"])
