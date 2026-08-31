import asyncio
import uuid
from urllib.parse import urljoin

import aiohttp
import pytest
from django.conf import settings

from pulpcore.client.pulp_file import FileFileDistribution, RepositoryAddRemoveContent


@pytest.mark.parallel
@pytest.mark.skipif(
    settings.REDIRECT_TO_OBJECT_STORAGE
    and not settings.storages["default"]["BACKEND"] == "pulpcore.app.models.storage.FileSystem",
    reason="Object-storage and redirect==True means response-headers aren't controlled by Pulp code.",
)
def test_response_headers(
    file_bindings,
    distribution_base_url,
    file_repo_with_auto_publish,
    gen_object_with_cleanup,
    monitor_task,
    tmp_path,
):
    blob = tmp_path / "blob"
    blob.write_bytes(b"response-headers-test")
    a_file = file_bindings.ContentFilesApi.upload(
        file=str(blob), relative_path=f"{uuid.uuid4()}.html"
    )

    data = RepositoryAddRemoveContent(add_content_units=[a_file.pulp_href])
    monitor_task(
        file_bindings.RepositoriesFileApi.modify(file_repo_with_auto_publish.pulp_href, data).task
    )

    data = FileFileDistribution(
        name=str(uuid.uuid4()),
        base_path=str(uuid.uuid4()),
        repository=file_repo_with_auto_publish.pulp_href,
    )
    distribution = gen_object_with_cleanup(file_bindings.DistributionsFileApi, data)
    distribution_base_url = distribution_base_url(distribution.base_url)

    async def do_test():
        async with aiohttp.ClientSession() as session:
            url = urljoin(distribution_base_url, a_file.relative_path)
            async with session.get(url) as response:
                hdrs = response.headers
                assert hdrs.get("Content-Disposition") and hdrs.get(
                    "Content-Disposition"
                ).startswith("attachment;filename=")
                assert hdrs.get("Content-Security-Policy") and "sandbox" in hdrs.get(
                    "Content-Security-Policy"
                )
                assert hdrs.get("X-Content-Type-Options") and "nosniff" in hdrs.get(
                    "X-Content-Type-Options"
                )

    asyncio.run(do_test())
