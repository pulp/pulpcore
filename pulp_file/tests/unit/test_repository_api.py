from datetime import timedelta
from secrets import token_hex
from urllib.parse import urlencode, urljoin, urlsplit

import pytest
from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from pulpcore.app.contexts import with_user
from pulpcore.app.models import RepositoryVersion, StagedContent, Task
from pulpcore.app.tasks import repository as repository_tasks
from pulpcore.app.util import get_prn, resolve, reverse

from pulp_file.app.models import FileContent, FileRepository
from pulp_file.app.viewsets import FileContentViewSet, FileRepositoryViewSet

AUTOCOMMIT_DELAY_SECONDS = 300


def update_repository(repository: FileRepository, *, autocommit: bool = False) -> None:
    repository.staging_enabled = True
    repository.staging_autocommit = autocommit
    repository.save(update_fields=["staging_enabled", "staging_autocommit"])


def create_file_content(relative_path: str, digest: str | None = None) -> FileContent:
    return FileContent.objects.create(
        relative_path=relative_path,
        digest=digest if digest is not None else token_hex(32),
    )


def get_detail_url(viewset, pk, trailing_path: str = "", query_params=None) -> str:
    """Return a viewset detail url with an optional trailing path and query parameters.

    Examples:
        FileRepositoryViewSet -> repositories/file/file/{pk}/
        FileContentViewSet -> content/file/file/{pk}/
    """
    url_name = viewset.view_name()
    detail_pattern = "{basename}-detail"
    url = urljoin(
        reverse(detail_pattern.format(basename=url_name), kwargs={"pk": pk}), trailing_path
    )
    return urlsplit(url)._replace(query=urlencode(query_params or {})).geturl()


def get_list_url(viewset, trailing_path: str = "") -> str:
    """Return a viewset list url with an optional trailing path.

    Examples:
        FileRepositoryViewSet -> repositories/file/file/
        FileContentViewSet -> content/file/file/
    """
    url_name = viewset.view_name()
    detail_pattern = "{basename}-list"
    return urljoin(reverse(detail_pattern.format(basename=url_name)), trailing_path)


@pytest.fixture
def repository(db):
    with with_user(None):
        return FileRepository.objects.create(name="file-repository-test")


@pytest.fixture
def api_client(db, django_user_model):
    user = django_user_model.objects.create_superuser(
        username="file-repository-test-admin",
        email="admin@example.com",
        password="test-password",
    )
    client = APIClient()
    client.force_authenticate(user=user)
    return client


class TestRepositoryEndpoint:
    def test_detail_exposes_default_staging_fields(self, api_client, repository):
        detail_url = get_detail_url(FileRepositoryViewSet, repository.pk)
        response = api_client.get(detail_url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["staging_enabled"] is False
        assert response.data["staging_autocommit"] is False
        assert "next_commit" not in response.data

    def test_list_exposes_staging_fields(self, api_client, repository):
        update_repository(repository, autocommit=True)

        list_url = get_list_url(FileRepositoryViewSet)
        response = api_client.get(list_url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1
        assert response.data["results"][0]["staging_enabled"] is True
        assert response.data["results"][0]["staging_autocommit"] is True
        assert "next_commit" not in response.data["results"][0]


class TestRepositoryNextCommit:
    @override_settings(STAGING_AUTOCOMMIT_DELAY_SECONDS=AUTOCOMMIT_DELAY_SECONDS)
    def test_staging_sets_deadline_only_after_autocommit_enabled(self, repository):
        update_repository(repository)
        assert repository.next_commit is None

        # Staging alone leaves the deadline unset
        repository.stage_file(create_file_content("without-autocommit.txt"))
        repository.refresh_from_db()
        assert repository.next_commit is None

        # The first staged file after enabling autocommit starts the delay
        update_repository(repository, autocommit=True)

        t_before = timezone.now() + timedelta(seconds=AUTOCOMMIT_DELAY_SECONDS)
        repository.stage_file(create_file_content("with-autocommit.txt"))
        t_after = timezone.now() + timedelta(seconds=AUTOCOMMIT_DELAY_SECONDS)

        repository.refresh_from_db()
        assert t_before <= repository.next_commit <= t_after

    def test_later_staged_file_keeps_first_deadline(self, repository):
        update_repository(repository, autocommit=True)

        repository.stage_file(create_file_content("first.txt"))
        repository.refresh_from_db()
        first_deadline = repository.next_commit
        assert first_deadline is not None

        # Later files do not postpone the pending commit
        repository.stage_file(create_file_content("second.txt"))
        repository.refresh_from_db()

        assert repository.next_commit == first_deadline


class TestRepositoryStagingEndpoint:
    @pytest.mark.parametrize(
        ("method", "query_params"),
        [
            ("get", {"relative_path": ""}),
            ("head", {"relative_path": ""}),
            ("get", {"relative_path": "nested/file.txt"}),
            ("head", {"relative_path": "nested/file.txt"}),
            ("get", {"path": "old-name.txt"}),
            ("head", {"path": "old-name.txt"}),
            ("post", {}),
            ("post", {"action": "invalid"}),
            ("post", {"action": "clear"}),
        ],
    )
    def test_invalid_query_params_returns_400(self, api_client, repository, method, query_params):
        """The methods should only accept valid query params."""
        update_repository(repository)
        url = get_detail_url(FileRepositoryViewSet, repository.pk, "staging/", query_params)
        request = getattr(api_client, method)

        response = request(url)

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.parametrize(
        ("method", "trailing_path", "query_params"),
        [
            ("get", "staging/", {}),
            ("head", "staging/", {}),
            ("get", "staging/missing.txt/", {}),
            ("head", "staging/missing.txt/", {}),
            ("post", "staging/", {"action": "commit"}),
            ("post", "staging/", {"action": "restore"}),
        ],
    )
    def test_staging_disabled_returns_404(
        self, api_client, repository, method, trailing_path, query_params
    ):
        """If repository has staging disabled, no action can be taken."""
        staging_url = get_detail_url(FileRepositoryViewSet, repository.pk, "staging/")

        # sanity check the staging_url exists
        assert resolve(staging_url)

        url = get_detail_url(FileRepositoryViewSet, repository.pk, trailing_path, query_params)
        request = getattr(api_client, method)
        response = request(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_staging_list_returns_paginated_content_urls(self, api_client, repository):
        update_repository(repository)
        staging_url = get_detail_url(FileRepositoryViewSet, repository.pk, "staging/")

        # Empty staging retains the pagination envelope
        empty_response = api_client.get(staging_url)
        assert empty_response.status_code == status.HTTP_200_OK
        assert empty_response.data == {
            "count": 0,
            "next": None,
            "previous": None,
            "results": [],
        }

        first = create_file_content("first.txt")
        second = create_file_content("nested/second.txt")
        repository.stage_file(first)
        repository.stage_file(second)

        response = api_client.get(staging_url)

        assert response.status_code == status.HTTP_200_OK
        assert set(response.data) == {"count", "next", "previous", "results"}
        assert response.data["count"] == 2

        # Results are ordered by content ID
        expected_urls = [
            get_detail_url(FileContentViewSet, content.pk)
            for content in sorted((first, second), key=lambda content: content.pk)
        ]
        assert response.data["results"] == expected_urls
        assert api_client.head(staging_url).status_code == status.HTTP_200_OK

        second_page_url = get_detail_url(
            FileRepositoryViewSet, repository.pk, "staging/", {"limit": "1", "offset": "1"}
        )
        second_page = api_client.get(second_page_url)
        assert second_page.status_code == status.HTTP_200_OK
        assert set(second_page.data) == {"count", "next", "previous", "results"}

        # Count covers the whole staging area, even on the second page
        assert second_page.data["count"] == 2
        assert second_page.data["results"] == expected_urls[1:]
        assert api_client.head(second_page_url).status_code == status.HTTP_200_OK

    def test_staging_path_get_and_head(self, api_client, repository):
        update_repository(repository)
        content = create_file_content("nested/file.txt")
        repository.stage_file(content)
        found_url = get_detail_url(FileRepositoryViewSet, repository.pk, "staging/nested/file.txt/")

        response = api_client.get(found_url)

        # Nested path segments are part of relative_path
        assert response.status_code == status.HTTP_200_OK
        assert response.data["pulp_href"] == get_detail_url(FileContentViewSet, content.pk)
        assert response.data["relative_path"] == content.relative_path
        assert api_client.head(found_url).status_code == status.HTTP_200_OK

        # Both methods report an unstaged path as missing
        missing_url = get_detail_url(FileRepositoryViewSet, repository.pk, "staging/missing.txt/")
        assert api_client.get(missing_url).status_code == status.HTTP_404_NOT_FOUND
        assert api_client.head(missing_url).status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.parametrize("action", ["commit", "restore"])
    def test_commit_and_restore_return_204_for_empty_staging(self, api_client, repository, action):
        update_repository(repository)
        url = get_detail_url(FileRepositoryViewSet, repository.pk, "staging/", {"action": action})
        task_count = Task.objects.count()

        response = api_client.post(url)

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert response.data is None
        assert Task.objects.count() == task_count

    @pytest.mark.parametrize("action", ["commit", "restore"])
    def test_commit_and_restore_return_tasks_for_staged_content(
        self, api_client, repository, action
    ):
        task_names = {
            "commit": "pulpcore.app.tasks.repository.commit_staging",
            "restore": "pulpcore.app.tasks.repository.restore_staging",
        }
        update_repository(repository)
        content = create_file_content("file.txt")
        repository.stage_file(content)
        url = get_detail_url(FileRepositoryViewSet, repository.pk, "staging/", {"action": action})

        response = api_client.post(url)

        # Staging actions return tasks
        assert response.status_code == status.HTTP_202_ACCEPTED
        task_pk = resolve(response.data["task"]).kwargs["pk"]
        task = Task.objects.get(pk=task_pk)
        assert response.data == {"task": reverse("tasks-detail", kwargs={"pk": task.pk})}
        assert task.name == task_names[action]
        assert task.enc_kwargs == {"repository_pk": str(repository.pk)}

        # Staging actions lock on the repository
        repository_prn = get_prn(repository)
        assert repository_prn in task.reserved_resources_record
        assert f"shared:{repository_prn}" not in task.reserved_resources_record


class TestRepositoryStagingTasks:
    def test_commit_creates_version_and_clears_staging_and_deadline(self, repository):
        update_repository(repository, autocommit=True)

        content = create_file_content("file.txt")
        repository.stage_file(content)
        repository.refresh_from_db()
        first_deadline = repository.next_commit
        assert first_deadline is not None

        repository_tasks.commit_staging(repository.pk)

        # Commit clears staging and the deadline, then creates a version
        repository.refresh_from_db()
        assert repository.latest_version().content.filter(pk=content.pk).exists()
        assert not StagedContent.objects.filter(repository=repository).exists()
        assert repository.next_commit is None

        # New staged content starts a new deadline
        repository.stage_file(create_file_content("later.txt"))
        repository.refresh_from_db()
        assert repository.next_commit > first_deadline

    def test_restore_clears_staging_and_deadline_without_new_version(self, repository):
        update_repository(repository, autocommit=True)

        initial_version = repository.latest_version()
        content = create_file_content("file.txt")
        repository.stage_file(content)
        repository.refresh_from_db()
        first_deadline = repository.next_commit
        assert first_deadline is not None

        repository_tasks.restore_staging(repository.pk)

        # Restore clears staging and the deadline without creating a version
        repository.refresh_from_db()
        assert repository.latest_version().pk == initial_version.pk
        assert not StagedContent.objects.filter(repository=repository).exists()
        assert repository.next_commit is None

        # New staged content starts a new deadline
        repository.stage_file(create_file_content("later.txt"))
        repository.refresh_from_db()
        assert repository.next_commit > first_deadline

    def test_failed_commit_preserves_staging_and_deadline(self, repository, monkeypatch):
        update_repository(repository, autocommit=True)

        content = create_file_content("file.txt")
        repository.stage_file(content)
        repository.refresh_from_db()
        deadline = repository.next_commit
        assert deadline is not None

        def fail_add_content(*args, **kwargs):
            raise RuntimeError("simulated commit failure")

        monkeypatch.setattr(RepositoryVersion, "add_content", fail_add_content)

        with pytest.raises(RuntimeError, match="simulated commit failure"):
            repository_tasks.commit_staging(repository.pk)

        # Failed commits leave the staged content and deadline available for retry
        repository.refresh_from_db()
        assert repository.next_commit == deadline
        assert StagedContent.objects.filter(repository=repository, content=content).exists()
