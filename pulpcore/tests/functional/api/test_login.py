import http
import pytest
import uuid

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
def session_user(pulpcore_bindings, gen_user, anonymous_user):
    old_cookie = pulpcore_bindings.client.cookie
    user = gen_user()
    with user:
        response = pulpcore_bindings.LoginApi.login_with_http_info()
        if isinstance(response, tuple):
            # old bindings
            _, _, headers = response
        else:
            # new bindings
            headers = response.headers
    cookie_jar = http.cookies.SimpleCookie(headers["Set-Cookie"])
    # Use anonymous_user to remove the basic auth header from the api client.
    with anonymous_user:
        pulpcore_bindings.client.cookie = "; ".join(
            (f"{k}={v.value}" for k, v in cookie_jar.items())
        )
        # Weird: You need to pass the CSRFToken as a header not a cookie...
        pulpcore_bindings.client.set_default_header("X-CSRFToken", cookie_jar["csrftoken"].value)
        yield user
        pulpcore_bindings.client.cookie = old_cookie


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
    assert pulpcore_bindings.client.configuration.username is None
    result = pulpcore_bindings.LoginApi.login_read()
    assert result.username == session_user.username


def test_session_cookie_object_create(
    pulpcore_bindings, session_user, gen_object_with_cleanup, pulp_admin_user
):
    # first assign create permission to the user
    role = "core.rbaccontentguard_creator"
    with pulp_admin_user:
        pulpcore_bindings.UsersRolesApi.create(
            auth_user_href=session_user.user.pulp_href,
            user_role={"role": role, "domain": None, "content_object": None},
        )
    # now try to create an object
    assert pulpcore_bindings.client.configuration.username is None
    gen_object_with_cleanup(pulpcore_bindings.ContentguardsRbacApi, {"name": str(uuid.uuid4())})


def test_logout_removes_sessionid(pulpcore_bindings, session_user):
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
