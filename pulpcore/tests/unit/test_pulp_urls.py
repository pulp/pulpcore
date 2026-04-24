import json

from pulpcore.app.find_url import find_api_root
from pulpcore.app.templatetags import pulp_urls


def test_urlize_basic_url():
    """
    Text starts with V3_API_ROOT. Should be made clickable.
    """
    _, curr_path = find_api_root(set_domain=False, rewrite_header=False)
    txt = f"{curr_path}foo/bar/"
    ret = pulp_urls.urlize(txt)
    assert ret == f'<a href="{txt}" rel="nofollow">{txt}</a>'


def test_urlize_quoted_href():
    """
    Text contains V3_API_ROOT in quotes. Should be made clickable.
    """
    _, curr_path = find_api_root(set_domain=False, rewrite_header=False)
    txt = json.dumps({"pulp_href": f"{curr_path}foo/bar/"})
    ret = pulp_urls.urlize(txt)
    assert ret == (
        f'{{&quot;pulp_href&quot;: &quot;<a href="{curr_path}foo/bar/" '
        f'rel="nofollow">{curr_path}foo/bar/</a>&quot;}}'
    )


def test_urlize_mixed_bag():
    """
    Text contains lots of stuff in json.
    """
    _, curr_path = find_api_root(set_domain=False, rewrite_header=False)
    txt = json.dumps(
        {
            "pulp_href": f"{curr_path}foo/bar/",
            "related": f"{curr_path}other/",
            "description": "Test XSS <script>alert('ALERT')</script>.",
        }
    )
    ret = pulp_urls.urlize(txt)
    assert ret == (
        f'{{&quot;pulp_href&quot;: &quot;<a href="{curr_path}foo/bar/" '
        f'rel="nofollow">{curr_path}foo/bar/</a>&quot;, '
        f'&quot;related&quot;: &quot;<a href="{curr_path}other/" '
        f'rel="nofollow">{curr_path}other/</a>&quot;, '
        "&quot;description&quot;: "
        "&quot;Test XSS &lt;script&gt;alert(&#x27;ALERT&#x27;)&lt;/script&gt;.&quot;}"
    )


def test_urlize_quoted_href_no_autoescape():
    """
    Text contains V3_API_ROOT in quotes. Should be made clickable.
    """
    _, curr_path = find_api_root(set_domain=False, rewrite_header=False)

    txt = json.dumps({"pulp_href": f"{curr_path}foo/bar/"})
    ret = pulp_urls.urlize(txt, autoescape=False)
    assert ret == (
        f'{{"pulp_href": "<a href="{curr_path}foo/bar/" rel="nofollow">{curr_path}foo/bar/</a>"}}'
    )


def test_urlize_url_xss_autoescape():
    """
    Text starts with API_ROOT, includes XSS. Should be made clickable, escape XSS.
    """
    _, curr_path = find_api_root(set_domain=False, rewrite_header=False)
    txt = f"{curr_path}foo/bar/<script>alert('ALERT!')</script>blech/"
    escapified_linked_text = (
        f'<a href="{curr_path}foo/bar/" rel="nofollow">{curr_path}foo/bar/</a>'
        "&lt;script&gt;alert(&#x27;ALERT!&#x27;)&lt;/script&gt;blech/"
    )
    ret = pulp_urls.urlize(txt)
    assert ret == escapified_linked_text


def test_urlize_url_xss_no_autoescape():
    """
    Text starts with API_ROOT, includes XSS. Should be made clickable, not escape XSS.
    """
    _, curr_path = find_api_root(set_domain=False, rewrite_header=False)
    txt = f"{curr_path}foo/bar/<script>alert('ALERT!')</script>blech/"
    escapified_linked_text = (
        f'<a href="{curr_path}foo/bar/" rel="nofollow">{curr_path}foo/bar/</a>'
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
