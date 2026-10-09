import os
import uuid

import pytest
from django.conf import settings

pytestmark = pytest.mark.skipif(not settings.DOMAIN_ENABLED, reason="Domains not enabled.")


@pytest.mark.parallel
def test_domain_admin_lists_all_domain_content(
    pulpcore_bindings,
    file_bindings,
    domain_factory,
    gen_user,
    monitor_task,
    tmp_path,
):
    domain = domain_factory()

    # Orphan content (not in any repository) uploaded into the domain, with a label.
    temp_file = tmp_path / str(uuid.uuid4())
    temp_file.write_bytes(os.urandom(128))
    created = monitor_task(
        file_bindings.ContentFilesApi.create(
            relative_path="a.txt",
            file=str(temp_file),
            pulp_domain=domain.name,
            pulp_labels={"key_a": "value_a"},
        ).task
    ).created_resources
    href = next(h for h in created if "/content/" in h)

    # A domain-scoped content admin (NOT a repository owner, NOT a superuser).
    user = gen_user(domain_roles=[("core.content_domain_viewer", domain.pulp_href)])

    with user:
        # Sees the orphan content via the domain-admin endpoint.
        result = pulpcore_bindings.ContentDomainsApi.list(pulp_domain=domain.name)
        assert result.count == 1
        assert result.results[0].pulp_href == href

        # Label filter works.
        filtered = pulpcore_bindings.ContentDomainsApi.list(
            pulp_domain=domain.name, pulp_label_select="key_a=value_a"
        )
        assert filtered.count == 1
        no_match = pulpcore_bindings.ContentDomainsApi.list(
            pulp_domain=domain.name, pulp_label_select="key_a=nope"
        )
        assert no_match.count == 0

        # Contrast: the repository-scoped endpoint hides the orphan content.
        repo_scoped = pulpcore_bindings.ContentApi.list(pulp_domain=domain.name)
        assert repo_scoped.count == 0


@pytest.mark.parallel
def test_non_admin_denied(
    pulpcore_bindings,
    domain_factory,
    gen_user,
):
    domain = domain_factory()
    user = gen_user()  # no roles

    with user:
        with pytest.raises(pulpcore_bindings.ApiException) as ctx:
            pulpcore_bindings.ContentDomainsApi.list(pulp_domain=domain.name)
        assert ctx.value.status == 403


@pytest.mark.parallel
def test_admin_of_one_domain_denied_in_another(
    pulpcore_bindings,
    domain_factory,
    gen_user,
):
    domain_a = domain_factory()
    domain_b = domain_factory()
    # Domain admin for domain A only.
    user = gen_user(domain_roles=[("core.content_domain_viewer", domain_a.pulp_href)])

    with user:
        # Allowed in the domain they administer.
        pulpcore_bindings.ContentDomainsApi.list(pulp_domain=domain_a.name)
        # Denied in a domain they do not administer.
        with pytest.raises(pulpcore_bindings.ApiException) as ctx:
            pulpcore_bindings.ContentDomainsApi.list(pulp_domain=domain_b.name)
        assert ctx.value.status == 403
