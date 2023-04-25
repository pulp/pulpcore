import pytest


@pytest.mark.parallel
def test_hidden_distros(file_distribution_factory, pulp_content_url, http_get):
    visible = [file_distribution_factory() for _ in range(5)]
    hidden = [file_distribution_factory(hidden=True) for _ in range(5)]

    content = http_get(pulp_content_url).decode("utf-8")

    for d in visible:
        assert content.count(f'a href="{d.base_path}/"') == 1
    for d in hidden:
        assert content.count(f'a href="{d.base_path}/"') == 0
