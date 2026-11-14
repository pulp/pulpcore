import json
from datetime import timedelta
from importlib import reload
from secrets import token_hex
from urllib.parse import urlencode, urljoin, urlsplit

import pytest
from django.apps import apps
from django.conf import settings as django_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import clear_url_caches
from django_guid import clear_guid, set_guid
from rest_framework import status
from rest_framework.test import APIClient

from pulpcore.app import urls as api_urls
from pulpcore.app.access_policy import AccessPolicyFromDB
from pulpcore.app.apps import _populate_access_policies
from pulpcore.app.contexts import with_user
from pulpcore.app.models import (
    AccessPolicy,
    RepositoryVersion,
    StagedContent,
    Task,
    TaskSchedule,
)
from pulpcore.app.role_util import assign_role
from pulpcore.app.tasks import repository as repository_tasks
from pulpcore.app.util import (
    configure_staging_autocommit,
    get_prn,
    get_view_urlpattern,
    resolve,
    reverse,
)
from pulpcore.openapi import PulpSchemaGenerator

from pulp_file.app.models import FileContent, FileRepository
from pulp_file.app.serializers import FileContentUploadSerializer
from pulp_file.app.viewsets import (
    FileContentViewSet,
    FileRepositoryStagingViewSet,
    FileRepositoryViewSet,
)


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


@pytest.fixture
def versioned_api_urls():
    rest_framework = {**django_settings.REST_FRAMEWORK, "ALLOWED_VERSIONS": ["v3", "v4"]}
    try:
        with override_settings(ENABLE_V4_API=True, REST_FRAMEWORK=rest_framework):
            reload(api_urls)
            clear_url_caches()
            yield
    finally:
        reload(api_urls)
        clear_url_caches()


class TestRepositoryEndpoint:
    def test_detail_exposes_default_staging_fields(self, api_client, repository):
        detail_url = get_detail_url(FileRepositoryViewSet, repository.pk)
        response = api_client.get(detail_url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["staging_enabled"] is False
        assert response.data["staging_autocommit"] is False

    def test_list_exposes_staging_fields(self, api_client, repository):
        update_repository(repository, autocommit=True)

        list_url = get_list_url(FileRepositoryViewSet)
        response = api_client.get(list_url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1
        assert response.data["results"][0]["staging_enabled"] is True
        assert response.data["results"][0]["staging_autocommit"] is True


class TestRepositoryStagingEndpoint:
    def test_staging_schema_has_collection_operations(self, db):
        schema = PulpSchemaGenerator().get_schema(public=True)
        staging_paths = {
            path: operations
            for path, operations in schema["paths"].items()
            if "file_file_repository_href" in path and path.endswith("staging/")
        }

        assert len(staging_paths) == 1
        operations = next(iter(staging_paths.values()))
        assert {"get", "post", "delete"} <= set(operations)
        get_schema = operations["get"]["responses"]["200"]["content"]["application/json"]["schema"]
        assert get_schema == {"$ref": "#/components/schemas/StagingListResponse"}
        assert schema["components"]["schemas"]["StagingListResponse"]["properties"]["results"] == {
            "type": "array",
            "items": {"type": "string"},
        }
        for method in ("post", "delete"):
            assert {"202", "204"} <= set(operations[method]["responses"])

    @pytest.mark.parametrize(
        ("method", "expected_status"),
        [
            ("get", status.HTTP_200_OK),
            ("head", status.HTTP_200_OK),
            ("post", status.HTTP_204_NO_CONTENT),
            ("delete", status.HTTP_204_NO_CONTENT),
        ],
    )
    def test_staging_accepts_version_route_parameter(
        self, api_client, repository, versioned_api_urls, method, expected_status
    ):
        update_repository(repository)
        url = get_detail_url(FileRepositoryViewSet, repository.pk, "staging/").replace(
            "/api/v3/", "/api/v4/"
        )
        assert resolve(url).kwargs["version"] == "v4"

        response = getattr(api_client, method)(url)

        assert response.status_code == expected_status

    def test_staging_access_follows_repository_roles(
        self, api_client, repository, django_user_model
    ):
        update_repository(repository)
        url = get_detail_url(FileRepositoryViewSet, repository.pk, "staging/")
        user = django_user_model.objects.create_user(username="staging-viewer")
        api_client.force_authenticate(user=user)

        assert api_client.get(url).status_code == status.HTTP_404_NOT_FOUND

        assign_role("file.filerepository_viewer", user, repository)
        assert api_client.get(url).status_code == status.HTTP_200_OK
        assert api_client.post(url).status_code == status.HTTP_403_FORBIDDEN
        assert api_client.delete(url).status_code == status.HTTP_403_FORBIDDEN

        assign_role("file.filerepository_owner", user, repository)
        assert api_client.post(url).status_code == status.HTTP_204_NO_CONTENT
        assert api_client.delete(url).status_code == status.HTTP_204_NO_CONTENT

    def test_customized_policy_keeps_staging_denied(self, api_client, repository, monkeypatch):
        update_repository(repository)
        policy = AccessPolicy.objects.get(
            viewset_name=get_view_urlpattern(FileRepositoryStagingViewSet)
        )
        policy.statements = []
        policy.customized = True
        policy.save(update_fields=["statements", "customized"])

        _populate_access_policies(sender=apps.get_app_config("file"), apps=apps, verbosity=0)

        policy.refresh_from_db()
        assert policy.statements == []
        url = get_detail_url(FileRepositoryViewSet, repository.pk, "staging/")
        # Viewsets capture the default permission class at import time; CI may use another one.
        monkeypatch.setattr(
            FileRepositoryStagingViewSet, "permission_classes", [AccessPolicyFromDB]
        )
        assert api_client.get(url).status_code == status.HTTP_403_FORBIDDEN

    def test_synchronous_upload_stages_only_for_enabled_repository(self, api_client, repository):
        upload_url = get_list_url(FileContentViewSet, "upload/")
        repository_url = get_detail_url(FileRepositoryViewSet, repository.pk)

        disabled = api_client.post(
            upload_url,
            {
                "file": SimpleUploadedFile("disabled.txt", b"disabled"),
                "relative_path": "disabled.txt",
                "repository": repository_url,
            },
            format="multipart",
        )
        assert disabled.status_code == status.HTTP_400_BAD_REQUEST
        assert StagedContent.objects.filter(repository=repository).count() == 0

        update_repository(repository)
        staged = api_client.post(
            upload_url,
            {
                "file": SimpleUploadedFile("staged.txt", b"staged"),
                "relative_path": "staged.txt",
                "repository": repository_url,
            },
            format="multipart",
        )
        assert staged.status_code == status.HTTP_201_CREATED
        assert StagedContent.objects.filter(repository=repository).count() == 1
        assert staged.data["relative_path"] == "staged.txt"
        assert repository.latest_version().number == 0

        orphan = api_client.post(
            upload_url,
            {"file": SimpleUploadedFile("orphan.txt", b"orphan"), "relative_path": "orphan.txt"},
            format="multipart",
        )
        assert orphan.status_code == status.HTTP_201_CREATED
        assert StagedContent.objects.filter(repository=repository).count() == 1

    def test_synchronous_upload_requires_repository_modify_permission(
        self, api_client, repository, django_user_model, monkeypatch
    ):
        update_repository(repository)
        validation_count = 0
        original_validate = FileContentUploadSerializer.validate

        def count_validation(serializer, data):
            nonlocal validation_count
            validation_count += 1
            return original_validate(serializer, data)

        monkeypatch.setattr(FileContentUploadSerializer, "validate", count_validation)
        user = django_user_model.objects.create_user(username="file-staging-uploader")
        assign_role("file.file_uploader", user)
        assign_role("file.filerepository_viewer", user, repository)
        api_client.force_authenticate(user=user)
        url = get_list_url(FileContentViewSet, "upload/")
        data = {
            "file": SimpleUploadedFile("restricted.txt", b"restricted"),
            "relative_path": "restricted.txt",
            "repository": get_detail_url(FileRepositoryViewSet, repository.pk),
        }

        assert (
            api_client.post(url, data, format="multipart").status_code == status.HTTP_403_FORBIDDEN
        )
        assert validation_count == 0

        assign_role("file.filerepository_owner", user, repository)
        data["file"] = SimpleUploadedFile("restricted.txt", b"restricted")
        assert api_client.post(url, data, format="multipart").status_code == status.HTTP_201_CREATED
        assert validation_count == 1
        assert StagedContent.objects.filter(repository=repository).count() == 1

    @pytest.mark.parametrize(
        ("method", "query_params"),
        [
            ("get", {"relative_path": ""}),
            ("head", {"relative_path": ""}),
            ("get", {"relative_path": "nested/file.txt"}),
            ("head", {"relative_path": "nested/file.txt"}),
            ("get", {"path": "old-name.txt"}),
            ("head", {"path": "old-name.txt"}),
            ("post", {"action": "commit"}),
            ("delete", {"action": "restore"}),
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
            ("post", "staging/", {}),
            ("delete", "staging/", {}),
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

    @pytest.mark.parametrize("method", ["post", "delete"])
    def test_commit_and_restore_return_204_for_empty_staging(self, api_client, repository, method):
        update_repository(repository)
        url = get_detail_url(FileRepositoryViewSet, repository.pk, "staging/")
        task_count = Task.objects.count()

        response = getattr(api_client, method)(url)

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert response.data is None
        assert Task.objects.count() == task_count

    @pytest.mark.parametrize("method", ["post", "delete"])
    def test_commit_and_restore_return_tasks_for_staged_content(
        self, api_client, repository, method
    ):
        task_names = {
            "post": "pulpcore.app.tasks.repository.commit_staging",
            "delete": "pulpcore.app.tasks.repository.restore_staging",
        }
        update_repository(repository)
        content = create_file_content("file.txt")
        repository.stage_file(content)
        url = get_detail_url(FileRepositoryViewSet, repository.pk, "staging/")

        response = getattr(api_client, method)(url)

        # Staging actions return tasks
        assert response.status_code == status.HTTP_202_ACCEPTED
        task_pk = resolve(response.data["task"]).kwargs["pk"]
        task = Task.objects.get(pk=task_pk)
        assert response.data == {"task": reverse("tasks-detail", kwargs={"pk": task.pk})}
        assert task.name == task_names[method]
        assert task.enc_kwargs == {"repository_pk": str(repository.pk)}

        # Staging actions lock on the repository
        repository_prn = get_prn(repository)
        assert repository_prn in task.reserved_resources_record
        assert f"shared:{repository_prn}" not in task.reserved_resources_record


class TestRepositoryStagingTasks:
    def test_commit_creates_version_and_clears_staging(self, repository):
        update_repository(repository, autocommit=True)

        content = create_file_content("file.txt")
        repository.stage_file(content)

        repository_tasks.commit_staging(repository.pk)

        # Commit clears staging and creates a version
        repository.refresh_from_db()
        assert repository.latest_version().content.filter(pk=content.pk).exists()
        assert not StagedContent.objects.filter(repository=repository).exists()

    def test_restore_clears_staging_without_new_version(self, repository):
        update_repository(repository, autocommit=True)

        initial_version = repository.latest_version()
        content = create_file_content("file.txt")
        repository.stage_file(content)
        repository_tasks.restore_staging(repository.pk)

        # Restore clears staging without creating a version
        repository.refresh_from_db()
        assert repository.latest_version().pk == initial_version.pk
        assert not StagedContent.objects.filter(repository=repository).exists()

    def test_failed_commit_preserves_staging(self, repository, monkeypatch):
        update_repository(repository, autocommit=True)

        content = create_file_content("file.txt")
        repository.stage_file(content)

        def fail_add_content(*args, **kwargs):
            raise RuntimeError("simulated commit failure")

        monkeypatch.setattr(RepositoryVersion, "add_content", fail_add_content)

        with pytest.raises(RuntimeError, match="simulated commit failure"):
            repository_tasks.commit_staging(repository.pk)

        # Failed commits leave the staged content available for retry
        assert StagedContent.objects.filter(repository=repository, content=content).exists()

    def test_content_staged_during_commit_remains_for_next_scan(self, repository, monkeypatch):
        update_repository(repository, autocommit=True)
        old = create_file_content("old.txt")
        newer = create_file_content("newer.txt")
        repository.stage_file(old)

        original_add_content = RepositoryVersion.add_content

        def stage_during_commit(version, *args, **kwargs):
            repository.stage_file(newer)
            return original_add_content(version, *args, **kwargs)

        monkeypatch.setattr(RepositoryVersion, "add_content", stage_during_commit)
        repository_tasks.commit_staging(repository.pk)

        assert repository.latest_version().content.filter(pk=old.pk).exists()
        assert not repository.latest_version().content.filter(pk=newer.pk).exists()
        assert list(
            StagedContent.objects.filter(repository=repository).values_list("content_id", flat=True)
        ) == [newer.pk]

        with with_user(None):
            set_guid(token_hex(16))
            try:
                task_ids = repository_tasks.dispatch_staging_autocommits()
            finally:
                clear_guid()

        assert len(task_ids) == 1
        assert Task.objects.get(pk=task_ids[0]).enc_kwargs == {"repository_pk": str(repository.pk)}


class TestRepositoryAutocommitScheduler:
    @staticmethod
    def create_repo_and_stage_content(*, autocommit: bool = True) -> FileRepository:
        with with_user(None):
            repository = FileRepository.objects.create(name=f"autocommit-{token_hex(8)}")
        update_repository(repository, autocommit=autocommit)
        repository.stage_file(create_file_content(f"{repository.name}.txt"))
        return repository

    def test_dispatches_due_repositories_with_serializable_task_ids(self, db):
        # These will trigger autocommit tasks
        due_repositories = (
            self.create_repo_and_stage_content(),
            self.create_repo_and_stage_content(),
        )
        # These won't trigger autocommit tasks
        with with_user(None):
            empty = FileRepository.objects.create(name=f"empty-autocommit-{token_hex(8)}")
        update_repository(empty, autocommit=True)
        self.create_repo_and_stage_content(autocommit=False)

        with with_user(None):
            set_guid(token_hex(16))
            try:
                task_ids = repository_tasks.dispatch_staging_autocommits()
                repeated_task_ids = repository_tasks.dispatch_staging_autocommits()
            finally:
                clear_guid()

        # Only due repositories with autocommit enabled receive commit tasks
        tasks = list(Task.objects.filter(name="pulpcore.app.tasks.repository.commit_staging"))
        assert len(tasks) == 2
        assert repeated_task_ids == []
        assert {task.enc_kwargs["repository_pk"] for task in tasks} == {
            str(due.pk) for due in due_repositories
        }

        # Task results contain serializable identifiers for the dispatched tasks
        assert isinstance(task_ids, list)
        assert len(task_ids) == len(tasks)
        assert set(task_ids) == {str(task.pk) for task in tasks}
        assert json.loads(json.dumps(task_ids)) == task_ids

        # Each commit task reserves its repository exclusively
        for task in tasks:
            due = next(
                due for due in due_repositories if str(due.pk) == task.enc_kwargs["repository_pk"]
            )
            repository_prn = get_prn(due)
            assert repository_prn in task.reserved_resources_record
            assert f"shared:{repository_prn}" not in task.reserved_resources_record

    def test_enabling_autocommit_includes_existing_staged_content(self, db):
        repository = self.create_repo_and_stage_content(autocommit=False)
        update_repository(repository, autocommit=True)

        with with_user(None):
            set_guid(token_hex(16))
            try:
                task_ids = repository_tasks.dispatch_staging_autocommits()
            finally:
                clear_guid()

        assert len(task_ids) == 1
        assert Task.objects.get(pk=task_ids[0]).enc_kwargs == {"repository_pk": str(repository.pk)}

    def test_scan_schedule_uses_configured_interval(self, db):
        name = "Scan repositories for staging autocommit"
        with override_settings(STAGING_AUTOCOMMIT_SCAN_INTERVAL_SECONDS=17):
            configure_staging_autocommit()

        schedule = TaskSchedule.objects.get(name=name)
        assert schedule.task_name == "pulpcore.app.tasks.repository.dispatch_staging_autocommits"
        assert schedule.dispatch_interval == timedelta(seconds=17)

        with override_settings(STAGING_AUTOCOMMIT_SCAN_INTERVAL_SECONDS=29):
            configure_staging_autocommit()

        schedule.refresh_from_db()
        assert TaskSchedule.objects.filter(name=name).count() == 1
        assert schedule.dispatch_interval == timedelta(seconds=29)
