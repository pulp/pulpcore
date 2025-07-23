import http
import pytest
import uuid

from urllib.parse import urlparse

pytestmark = [pytest.mark.parallel]


@pytest.fixture(autouse=True)
def _fix_response_headers(monkeypatch, pulpcore_bindings):
    """
    Fix bindings incorrectly translating HTTPHeaderDict to dict.
    Ideally they wouldn't even make it a dict, but keep it whatever case insensitive multivalued
    mapping the underlying http adapter provides. Alternatively translate everything into the
    mutidict.CIMultiDict type.
    """
    monkeypatch.setattr(
        pulpcore_bindings.module.rest.RESTResponse,
        "getheaders",
        lambda self: dict(self.response.headers),
    )


@pytest.fixture
def session_user(pulpcore_bindings, gen_user, bindings_cfg):
    class SessionUser(gen_user):
        def __enter__(self):
            """
            Mimic the behavior of a session user (aka what browsers do).

            - Set auth to None so client will use the session cookie
            - Set X-CSRFToken header since we are posting JSON instead of form data
            (Django creates a hidden input field for the CSRF token when using forms)
            - Set Origin and Host headers so Django CSRF middleware will allow the request
            (Browsers send these headers and it is needed when using HTTPS)
            """
            self.old_cookie = pulpcore_bindings.client.cookie
            super().__enter__()
            response = pulpcore_bindings.LoginApi.login_with_http_info()
            if isinstance(response, tuple):
                # old bindings
                _, _, headers = response
            else:
                # new bindings
                headers = response.headers
            cookie_jar = http.cookies.SimpleCookie(headers["Set-Cookie"])
            self.cookie = "; ".join((f"{k}={v.value}" for k, v in cookie_jar.items()))
            self.csrf_token = cookie_jar["csrftoken"].value
            self.session_id = cookie_jar["sessionid"].value
            bindings_cfg.username, bindings_cfg.password = None, None
            pulpcore_bindings.client.cookie = self.cookie
            pulpcore_bindings.client.set_default_header("X-CSRFToken", self.csrf_token)
            pulpcore_bindings.client.set_default_header("Origin", bindings_cfg.host)
            pulpcore_bindings.client.set_default_header("Host", urlparse(bindings_cfg.host).netloc)
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            super().__exit__(exc_type, exc_value, traceback)
            pulpcore_bindings.client.cookie = self.old_cookie

    return SessionUser


def test_login_read_denies_anonymous(pulpcore_bindings, anonymous_user):
    with anonymous_user:
        with pytest.raises(pulpcore_bindings.module.ApiException) as exc:
            pulpcore_bindings.LoginApi.login_read()
    assert exc.value.status == 401


def test_login_read_returns_username(pulpcore_bindings, gen_user):
    user = gen_user()
    with user:
        result = pulpcore_bindings.LoginApi.login_read()
    assert result.username == user.username


def test_login_denies_anonymous(pulpcore_bindings, anonymous_user):
    with anonymous_user:
        with pytest.raises(pulpcore_bindings.module.ApiException) as exc:
            pulpcore_bindings.LoginApi.login()
    assert exc.value.status == 401


def test_login_sets_session_cookie(pulpcore_bindings, gen_user):
    user = gen_user()
    with user:
        response = pulpcore_bindings.LoginApi.login_with_http_info()
        if isinstance(response, tuple):
            # old bindings
            result, status_code, headers = response
        else:
            # new bindings
            result = response.data
            status_code = response.status_code
            headers = response.headers
    assert status_code == 201
    assert result.username == user.username
    cookie_jar = http.cookies.SimpleCookie(headers["Set-Cookie"])
    assert cookie_jar["sessionid"].value != ""
    assert cookie_jar["csrftoken"].value != ""


def test_session_cookie_is_authorization(pulpcore_bindings, session_user):
    with session_user() as user:
        result = pulpcore_bindings.LoginApi.login_read()
        assert result.username == user.username
        assert pulpcore_bindings.client.configuration.username is None


def test_session_cookie_object_create(pulpcore_bindings, session_user, gen_object_with_cleanup):
    with session_user(model_roles=["core.rbaccontentguard_creator"]):
        assert pulpcore_bindings.client.configuration.username is None
        gen_object_with_cleanup(pulpcore_bindings.ContentguardsRbacApi, {"name": str(uuid.uuid4())})


def test_logout_removes_sessionid(pulpcore_bindings, session_user):
    with session_user() as user:
        assert user.session_id != ""
        assert user.session_id in pulpcore_bindings.client.cookie
        response = pulpcore_bindings.LoginApi.logout_with_http_info()
        if isinstance(response, tuple):
            # old bindings
            _, status_code, headers = response
        else:
            # new bindings
            status_code = response.status_code
            headers = response.headers
    assert status_code == 204
    cookie_jar = http.cookies.SimpleCookie(headers["Set-Cookie"])
    assert cookie_jar["sessionid"].value == ""


def test_logout_denies_anonymous(pulpcore_bindings, anonymous_user):
    with anonymous_user:
        with pytest.raises(pulpcore_bindings.module.ApiException) as exc:
            pulpcore_bindings.LoginApi.logout()
    assert exc.value.status == 401
