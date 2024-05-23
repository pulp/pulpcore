import aiohttp
import asyncio
import pytest
import uuid

from urllib.parse import urljoin

from pulpcore.client.pulp_file import FileFileDistribution, RepositoryAddRemoveContent


@pytest.mark.parallel
def test_content_types(
    file_bindings,
    file_repo_with_auto_publish,
    file_content_unit_with_name_factory,
    gen_object_with_cleanup,
    monitor_task,
):
    """Test if content-app correctly returns mime-types based on filenames."""
    files = {
        "tar.gz": file_content_unit_with_name_factory(f"{str(uuid.uuid4())}.tar.gz"),
        "xml.gz": file_content_unit_with_name_factory(f"{str(uuid.uuid4())}.xml.gz"),
        "xml.bz2": file_content_unit_with_name_factory(f"{str(uuid.uuid4())}.xml.bz2"),
        "xml.zstd": file_content_unit_with_name_factory(f"{str(uuid.uuid4())}.xml.zstd"),
        "xml.xz": file_content_unit_with_name_factory(f"{str(uuid.uuid4())}.xml.xz"),
        "json.zstd": file_content_unit_with_name_factory(f"{str(uuid.uuid4())}.json.zstd"),
        "json": file_content_unit_with_name_factory(f"{str(uuid.uuid4())}.json"),
        "txt": file_content_unit_with_name_factory(f"{str(uuid.uuid4())}.txt"),
        "xml": file_content_unit_with_name_factory(f"{str(uuid.uuid4())}.xml"),
        "jpg": file_content_unit_with_name_factory(f"{str(uuid.uuid4())}.jpg"),
        "JPG": file_content_unit_with_name_factory(f"{str(uuid.uuid4())}.JPG"),
        "halabala": file_content_unit_with_name_factory(f"{str(uuid.uuid4())}.halabala"),
        "noextension1": file_content_unit_with_name_factory(f"{str(uuid.uuid4())}.asd/.asd/a"),
        "noextension2": file_content_unit_with_name_factory(f"{str(uuid.uuid4())}.....f"),
    }

    units_to_add = list(map(lambda f: f.pulp_href, files.values()))
    data = RepositoryAddRemoveContent(add_content_units=units_to_add)
    monitor_task(
        file_bindings.RepositoriesFileApi.modify(file_repo_with_auto_publish.pulp_href, data).task
    )

    data = FileFileDistribution(
        name=str(uuid.uuid4()),
        base_path=str(uuid.uuid4()),
        repository=file_repo_with_auto_publish.pulp_href,
    )
    distribution = gen_object_with_cleanup(file_bindings.DistributionsFileApi, data)

    received_mimetypes = {}
    for extension, content_unit in files.items():

        async def get_content_type():
            async with aiohttp.ClientSession() as session:
                url = urljoin(distribution.base_url, content_unit.relative_path)
                async with session.get(url) as response:
                    return response.headers.get("Content-Type")

        content_type = asyncio.run(get_content_type())
        received_mimetypes[extension] = content_type

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
