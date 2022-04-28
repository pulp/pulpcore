from uuid import uuid4

import pytest

from pulpcore.client.pulpcore.exceptions import ApiException


def test_cancel_invalid_task_raises_404(pulp_api_v3_path, tasks_api_client):
    patched_task_cancel = {"state": "canceled"}

    missing_task_url = f"{pulp_api_v3_path}tasks/{uuid4()}/"

    with pytest.raises(ApiException) as e_info:
        tasks_api_client.tasks_cancel(
            task_href=missing_task_url, patched_task_cancel=patched_task_cancel
        )
    assert e_info.value.status == 404
