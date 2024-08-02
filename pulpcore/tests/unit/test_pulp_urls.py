import pytest
import json

from pulpcore.app.templatetags import pulp_urls


@pytest.fixture(autouse=True)
def api_root(settings):
    settings.DOMAIN_ENABLED = True
    # TODO: dynaconf lazy settings...
    # settings.API_ROOT = "/baz/"
    settings.V3_API_ROOT = "/baz/api/v3/"


def test_urlize_basic_url():
    """
    Text starts with V3_API_ROOT. Should be made clickable.
    """
    txt = "/baz/api/v3/foo/bar/"
    ret = pulp_urls.urlize(txt)
    assert ret == f'<a href="{txt}" rel="nofollow">{txt}</a>'


def test_urlize_quoted_href():
    """
    Text contains V3_API_ROOT in quotes. Should be made clickable.
    """
    txt = json.dumps({"pulp_href": "/baz/api/v3/foo/bar/"})
    ret = pulp_urls.urlize(txt)
    assert ret == (
        '{&quot;pulp_href&quot;: &quot;<a href="/baz/api/v3/foo/bar/" '
        'rel="nofollow">/baz/api/v3/foo/bar/</a>&quot;}'
    )


def test_urlize_mixed_bag():
    """
    Text contains lots of stuff in json.
    """
    txt = json.dumps(
        {
            "pulp_href": "/baz/api/v3/foo/bar/",
            "related": "/baz/api/v3/other/",
            "description": "Test XSS <script>alert('ALERT')</script>.",
        }
    )
    ret = pulp_urls.urlize(txt)
    assert ret == (
        '{&quot;pulp_href&quot;: &quot;<a href="/baz/api/v3/foo/bar/" '
        'rel="nofollow">/baz/api/v3/foo/bar/</a>&quot;, '
        '&quot;related&quot;: &quot;<a href="/baz/api/v3/other/" '
        'rel="nofollow">/baz/api/v3/other/</a>&quot;, '
        "&quot;description&quot;: "
        "&quot;Test XSS &lt;script&gt;alert(&#x27;ALERT&#x27;)&lt;/script&gt;.&quot;}"
    )


def test_urlize_quoted_href_no_autoescape():
    """
    Text contains V3_API_ROOT in quotes. Should be made clickable.
    """
    txt = json.dumps({"pulp_href": "/baz/api/v3/foo/bar/"})
    ret = pulp_urls.urlize(txt, autoescape=False)
    assert ret == (
        '{"pulp_href": "<a href="/baz/api/v3/foo/bar/" rel="nofollow">/baz/api/v3/foo/bar/</a>"}'
    )


def test_urlize_url_xss_autoescape():
    """
    Text starts with API_ROOT, includes XSS. Should be made clickable, escape XSS.
    """
    txt = "/baz/api/v3/foo/bar/<script>alert('ALERT!')</script>blech/"
    escapified_linked_text = (
        '<a href="/baz/api/v3/foo/bar/" rel="nofollow">/baz/api/v3/foo/bar/</a>'
        "&lt;script&gt;alert(&#x27;ALERT!&#x27;)&lt;/script&gt;blech/"
    )
    ret = pulp_urls.urlize(txt)
    assert ret == escapified_linked_text


def test_urlize_url_xss_no_autoescape():
    """
    Text starts with API_ROOT, includes XSS. Should be made clickable, not escape XSS.
    """
    txt = "/baz/api/v3/foo/bar/<script>alert('ALERT!')</script>blech/"
    escapified_linked_text = (
        '<a href="/baz/api/v3/foo/bar/" rel="nofollow">/baz/api/v3/foo/bar/</a>'
        "<script>alert('ALERT!')</script>blech/"
    )
    ret = pulp_urls.urlize(txt, autoescape=False)
    assert ret == escapified_linked_text


def test_urlize_autoescape():
    """
    Text contains XSS. Expect escaped.
    """
    txt = "foo/bar/<script>alert('ALERT!')</script>blech/"
    ret = pulp_urls.urlize(txt)
    assert ret == "foo/bar/&lt;script&gt;alert(&#x27;ALERT!&#x27;)&lt;/script&gt;blech/"


def test_urlize_no_autoescape():
    """
    Text contains XSS. Expect not escaped.
    """
    txt = "foo/bar/<script>alert('ALERT!')</script>blech/"
    ret = pulp_urls.urlize(txt, autoescape=False)
    assert ret == txt
