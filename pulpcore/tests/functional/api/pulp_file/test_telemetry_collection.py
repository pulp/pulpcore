import requests
import uuid

from urllib.parse import urljoin, urlparse
from django.conf import settings

from pulpcore.client.pulp_file import FileFileDistribution, RepositoryAddRemoveContent


def test_get_requests(
    file_distribution_api_client,
    file_bindings,
    file_repo_with_auto_publish,
    file_content_unit_with_name_factory,
    gen_object_with_cleanup,
    monitor_task,
    received_otel_span,
    test_path,
):
    """Test if content-app correctly returns mime-types based on filenames."""
    content_units = [
        file_content_unit_with_name_factory("otel_test_file1.tar.gz"),
        file_content_unit_with_name_factory("otel_test_file2.xml.gz"),
        file_content_unit_with_name_factory("otel_test_file3.txt"),
    ]
    units_to_add = list(map(lambda f: f.pulp_href, content_units))
    data = RepositoryAddRemoveContent(add_content_units=units_to_add)
    monitor_task(
        file_bindings.RepositoriesFileApi.modify(file_repo_with_auto_publish.pulp_href, data).task
    )

    data = FileFileDistribution(
        name=str(uuid.uuid4()),
        base_path=str(uuid.uuid4()),
        repository=file_repo_with_auto_publish.pulp_href,
    )
    distribution = gen_object_with_cleanup(file_distribution_api_client, data)

    for content_unit in content_units:
        url = urljoin(distribution.base_url, content_unit.relative_path)
        content_path = urlparse(url).path

        s = requests.Session()
        s.headers = {"User-Agent": test_path}

        if (
            settings.DEFAULT_FILE_STORAGE != "pulpcore.app.models.storage.FileSystem"
            and settings.REDIRECT_TO_OBJECT_STORAGE
        ):
            status_code = 302
        else:
            status_code = 200

        s.get(url, allow_redirects=False)
        assert received_otel_span(
            {
                "http.method": "GET",
                "http.target": content_path,
                "http.status_code": status_code,
                "http.user_agent": test_path,
            }
        )

        s.get(url + "fail")
        assert received_otel_span(
            {
                "http.method": "GET",
                "http.target": content_path + "fail",
                "http.status_code": 404,
                "http.user_agent": test_path,
            }
        )

        s.post(url, data={})
        assert received_otel_span(
            {
                "http.method": "POST",
                "http.target": content_path,
                "http.status_code": 405,
                "http.user_agent": test_path,
            }
        )

        s.head(url, allow_redirects=False)
        assert received_otel_span(
            {
                "http.method": "HEAD",
                "http.target": content_path,
                "http.status_code": status_code,
                "http.user_agent": test_path,
            }
        )
