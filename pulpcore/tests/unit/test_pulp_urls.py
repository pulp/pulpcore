import pytest
from django.conf import settings

from pulpcore.app.templatetags import pulp_urls

pytestmark = pytest.mark.usefixtures("fake_domain")


def test_urlize_quoted_hrefs_basic_url():
    """
    text starts with API_ROOT, defaults. Should be made clickable
    """
    txt = settings.V3_API_ROOT + "foo/bar/"
    ret = pulp_urls.urlize_quoted_hrefs(txt)
    assert ret == f'<a href="{txt}" rel="nofollow">{txt}</a>'


def test_urlize_quoted_hrefs_nofollow():
    """
    text starts with API_ROOT, defaults. Should be made clickable
    """
    txt = settings.V3_API_ROOT + "foo/bar/"
    ret = pulp_urls.urlize_quoted_hrefs(txt, nofollow=False)
    assert ret == f'<a href="{txt}">{txt}</a>'


def test_urlize_quoted_hrefs_trim():
    """
    text starts with API_ROOT, defaults. Should be made clickable
    """
    txt = settings.V3_API_ROOT + "foo/bar/"
    trim_txt = txt[0] + "..."
    ret = pulp_urls.urlize_quoted_hrefs(txt, trim_url_limit=4)
    assert ret == f'<a href="{txt}" rel="nofollow">{trim_txt}</a>'


def test_urlize_quoted_hrefs_basic_url_xss():
    """
    text starts with API_ROOT, includes XSS, defaults. Should be made clickable, escape XSS
    """
    txt = settings.V3_API_ROOT + "foo/bar/<script>alert('ALERT!')</script>blech/"
    escapified_linked_text = (
        '<a href="' + settings.V3_API_ROOT + "foo/bar/"
        '%3Cscript%3Ealert(&#x27;ALERT!&#x27;)%3C/script%3Eblech/" '
        'rel="nofollow">' + settings.V3_API_ROOT + "foo/bar/&lt;script&gt;"
        "alert(&#x27;ALERT!&#x27;)&lt;/script&gt;blech/</a>"
    )
    ret = pulp_urls.urlize_quoted_hrefs(txt)
    assert ret == escapified_linked_text


def test_urlize_quoted_hrefs_basic_escape():
    """
    text contains XSS. Expect escaped
    """
    txt = "foo/bar/<script>alert('ALERT!')</script>blech/"
    ret = pulp_urls.urlize_quoted_hrefs(txt)
    assert ret == "foo/bar/&lt;script&gt;alert(&#x27;ALERT!&#x27;)&lt;/script&gt;blech/"
