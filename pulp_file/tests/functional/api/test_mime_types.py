import asyncio
import uuid
from urllib.parse import urljoin

import aiohttp
import pytest

from pulpcore.client.pulp_file import FileFileDistribution, RepositoryAddRemoveContent


@pytest.mark.parallel
def test_content_types(
    file_bindings,
    distribution_base_url,
    file_repo_with_auto_publish,
    gen_object_with_cleanup,
    monitor_task,
    tmp_path,
):
    """Test if content-app correctly returns mime-types based on filenames."""
    relative_paths = {
        "tar.gz": f"{uuid.uuid4()}.tar.gz",
        "xml.gz": f"{uuid.uuid4()}.xml.gz",
        "xml.bz2": f"{uuid.uuid4()}.xml.bz2",
        "xml.zstd": f"{uuid.uuid4()}.xml.zstd",
        "xml.xz": f"{uuid.uuid4()}.xml.xz",
        "json.zstd": f"{uuid.uuid4()}.json.zstd",
        "json": f"{uuid.uuid4()}.json",
        "txt": f"{uuid.uuid4()}.txt",
        "xml": f"{uuid.uuid4()}.xml",
        "jpg": f"{uuid.uuid4()}.jpg",
        "JPG": f"{uuid.uuid4()}.JPG",
        "halabala": f"{uuid.uuid4()}.halabala",
        "noextension1": f"{uuid.uuid4()}.asd/.asd/a",
        "noextension2": f"{uuid.uuid4()}.....f",
    }

    blob = tmp_path / "blob"
    blob.write_bytes(b"mime-type-test")
    files = {
        extension: file_bindings.ContentFilesApi.upload(file=str(blob), relative_path=relative_path)
        for extension, relative_path in relative_paths.items()
    }

    data = RepositoryAddRemoveContent(add_content_units=[f.pulp_href for f in files.values()])
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

    async def fetch_mimetypes():
        async with aiohttp.ClientSession() as session:

            async def get_content_type(extension, content_unit):
                url = urljoin(distribution_base_url, content_unit.relative_path)
                async with session.get(url) as response:
                    return extension, response.headers.get("Content-Type")

            pairs = await asyncio.gather(
                *(get_content_type(ext, unit) for ext, unit in files.items())
            )
        return dict(pairs)

    received_mimetypes = asyncio.run(fetch_mimetypes())
    expected_mimetypes = {
        "tar.gz": "application/gzip",
        "xml.gz": "application/gzip",
        "xml.bz2": "application/x-bzip2",
        "xml.zstd": "application/zstd",
        "xml.xz": "application/x-xz",
        "json.zstd": "application/zstd",
        "json": "application/json",
        "txt": "text/plain",
        "xml": "text/xml",
        "jpg": "image/jpeg",
        "JPG": "image/jpeg",
        # The application/octet-stream MIME type is used for unknown binary files
        "halabala": "application/octet-stream",
        "noextension1": "application/octet-stream",
        "noextension2": "application/octet-stream",
    }
    assert received_mimetypes == expected_mimetypes
