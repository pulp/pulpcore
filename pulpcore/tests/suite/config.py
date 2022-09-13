# coding=utf-8
"""Tools for managing information about hosts under test.

Pulp Smash needs to know about the Pulp application under test and the hosts
that comprise that application. For example, it might need to know which
username and password to use when communicating with a Pulp application, or it
might need to know which host is hosting the squid service, if any. This module
eases the task of managing that information.
"""
import aiohttp
import collections
import json
import os
import warnings
from copy import deepcopy
from urllib.parse import urlunsplit

import jsonschema
from packaging.version import Version
from xdg import BaseDirectory

from pulpcore.client.pulpcore import Configuration

PULP_FIXTURES_BASE_URL = "https://fixtures.pulpproject.org/"


def _get_pulp_2_api_role():
    """Return a schema definition for the Pulp 2 "api" role."""
    return {
        "required": ["scheme"],
        "type": "object",
        "properties": {
            "port": {"type": "integer", "minimum": 0, "maximum": 65535},
            "scheme": {"enum": ["http", "https"], "type": "string"},
            "service": {"type": "string"},
            "verify": {"type": ["boolean", "string"]},
        },
    }


def _get_pulp_3_api_role():
    """Return a schema definition for the Pulp 3 "api" role."""
    api_role = _get_pulp_2_api_role()
    api_role["required"].append("service")
    return api_role


def _get_pulp_3_content_role():
    """Return a schema definition for the Pulp 3 "content" role."""
    content_role = _get_pulp_3_api_role()
    content_role["required"].remove("service")
    content_role["properties"]["service"] = {"type": "string"}
    return content_role


# `get_config` uses this as a cache. It is intentionally a global. This design
# lets us do interesting things like flush the cache at run time or completely
# avoid a config file by fetching values from the UI.
_CONFIG = None

P3_REQUIRED_ROLES = {
    "api",
    "pulp resource manager",
    "pulp workers",
    "redis",
}
"""The set of roles that must be present in a functional Pulp 3 application."""

P3_OPTIONAL_ROLES = {"content", "custom"}
"""Additional roles that can be present in a Pulp 3 application."""

P3_ROLES = P3_REQUIRED_ROLES.union(P3_OPTIONAL_ROLES)
"""The set of all roles that can be present in a Pulp 3 application."""

JSON_CONFIG_SCHEMA = {
    "title": "Pulp Smash configuration file",
    "anyOf": [
        {
            "additionalProperties": False,
            "required": ["pulp", "hosts"],
            "type": "object",
            "properties": {
                "hosts": {
                    "type": "array",
                    "minItems": 1,
                    "items": {"$ref": "#/definitions/pulp 2 host"},
                },
                "pulp": {"$ref": "#/definitions/pulp"},
                "general": {"$ref": "#/definitions/general"},
                "custom": {"$ref": "#/definitions/custom"},
            },
        },
        {
            "additionalProperties": False,
            "required": ["pulp", "hosts"],
            "type": "object",
            "properties": {
                "hosts": {
                    "type": "array",
                    "minItems": 1,
                    "items": {"$ref": "#/definitions/pulp 3 host"},
                },
                "pulp": {"$ref": "#/definitions/pulp"},
                "general": {"$ref": "#/definitions/general"},
                "custom": {"$ref": "#/definitions/custom"},
            },
        },
    ],
    "definitions": {
        "pulp": {
            "additionalProperties": False,
            "required": ["auth", "version"],
            "type": "object",
            "properties": {
                "auth": {"type": "array", "maxItems": 2, "minItems": 2},
                "version": {"type": "string"},
                "selinux enabled": {"type": "boolean"},
            },
        },
        "custom": {"type": "object"},
        "general": {
            "additionalProperties": False,
            "required": ["timeout"],
            "type": "object",
            "properties": {"timeout": {"type": "number", "mininum": 1, "maximum": 1800}},
        },
        "pulp 3 host": {
            "additionalProperties": False,
            "required": ["hostname", "roles"],
            "type": "object",
            "properties": {
                "hostname": {"type": "string", "format": "hostname"},
                "roles": {
                    "additionalProperties": False,
                    "type": "object",
                    "properties": {
                        "api": {"$ref": "#/definitions/pulp 3 api role"},
                        "content": {"$ref": "#/definitions/pulp 3 content role"},
                        "pulp resource manager": {
                            "$ref": "#/definitions/pulp resource manager role"
                        },
                        "pulp workers": {"$ref": "#/definitions/pulp workers role"},
                        "redis": {"$ref": "#/definitions/redis role"},
                    },
                },
            },
        },
        "pulp 3 api role": _get_pulp_3_api_role(),
        "pulp 3 content role": _get_pulp_3_content_role(),
        "mongod role": {"type": "object"},
        "pulp celerybeat role": {"type": "object"},
        "pulp cli role": {"type": "object"},
        "pulp resource manager role": {"type": "object"},
        "pulp workers role": {"type": "object"},
        "redis role": {"type": "object"},
        "squid role": {"type": "object"},
    },
}
"""The schema for Pulp Smash's configuration file."""


def _public_attrs(obj):
    """Return a copy of the public elements in ``vars(obj)``."""
    return {key: val for key, val in vars(obj).copy().items() if not key.startswith("_")}


def get_config():
    """Return a copy of the global ``PulpSmashConfig`` object.

    This method makes use of a cache. If the cache is empty, the configuration
    file is parsed and the cache is populated. Otherwise, a copy of the cached
    configuration object is returned.

    :returns: A copy of the global server configuration object.
    :rtype: pulp_smash.config.PulpSmashConfig
    """
    global _CONFIG  # pylint:disable=global-statement
    if _CONFIG is None:
        _CONFIG = PulpSmashConfig.load()
    return deepcopy(_CONFIG)


def validate_config(config_dict):
    """Validate a config against :data:`pulp_smash.config.JSON_CONFIG_SCHEMA`.

    :param config_dict: A dict, such as one returned by calling ``json.load``
        on a configuration file, or one generated by the user-facing CLI.
    :returns: Nothing.
    :raises pulp_smash.exceptions.ConfigValidationError: If the any validation
        error is found.
    """
    try:
        jsonschema.validate(config_dict, JSON_CONFIG_SCHEMA)
    except jsonschema.exceptions.ValidationError as err:
        raise RuntimeError(err.message) from err

    # The schema is capable of defining what roles must be fulfilled by *every*
    # host in a Pulp deployment. But it's not capable of defining which roles
    # must be fulfilled by the roles in a Pulp deployment *in aggregate*. The
    # latter is done here.
    config_roles = set()
    for host in config_dict["hosts"]:
        config_roles.update(set(host["roles"].keys()))
    required_roles = P3_REQUIRED_ROLES
    if not required_roles.issubset(config_roles):
        raise RuntimeError(
            "The following roles are not fulfilled by any hosts: {}".format(
                ", ".join(sorted(required_roles - config_roles))
            )
        )


# Representation of a host and its roles."""
PulpHost = collections.namedtuple("PulpHost", "hostname roles")


class PulpSmashConfig:
    """Information about a Pulp application.

    This object stores information about Pulp application and its constituent
    hosts. A single Pulp application may have its services spread across
    several hosts. For example, one host might run Qpid, another might run
    MongoDB, and so on. Here's how to model a multi-host deployment where
    Apache runs on one host, and the remaining components run on another host:

    >>> import requests
    >>> from pulp_smash.config import PulpSmashConfig
    >>> cfg = PulpSmashConfig(
    ...     pulp_auth=('username', 'password'),
    ...     pulp_version='2.12.2',
    ...     pulp_selinux_enabled=True,
    ...     aiohttp_fixtures_origin="127.0.0.1",
    ...     hosts=[
    ...         PulpHost(
    ...             hostname='pulp1.example.com',
    ...             roles={'api': {'scheme': 'https'}},
    ...         ),
    ...         PulpHost(
    ...             hostname='pulp.example.com',
    ...             roles={
    ...                 'amqp broker': {'service': 'qpidd'},
    ...                 'mongod': {},
    ...                 'pulp celerybeat': {},
    ...                 'pulp resource manager': {},
    ...                 'pulp workers': {},
    ...             },
    ...         )
    ...     ]
    ... )

    In the simplest case, all of the services that comprise a Pulp applicaiton
    run on a single host. Here's an example of how this object might model a
    single-host deployment:

    >>> import requests
    >>> from pulp_smash.config import PulpSmashConfig
    >>> cfg = PulpSmashConfig(
    ...     pulp_auth=('username', 'password'),
    ...     pulp_version='2.12.2',
    ...     pulp_selinux_enabled=True,
    ...     aiohttp_fixtures_origin="127.0.0.1",
    ...     hosts=[
    ...         PulpHost(
    ...             hostname='pulp.example.com',
    ...             roles={
    ...                 'amqp broker': {'service': 'qpidd'},
    ...                 'api': {'scheme': 'https'},
    ...                 'mongod': {},
    ...                 'pulp cli': {},
    ...                 'pulp celerybeat': {},
    ...                 'pulp resource manager': {},
    ...                 'pulp workers': {},
    ...             },
    ...         )
    ...     ]
    ... )

    In the simplest case, Pulp Smash's configuration file resides at
    ``~/.config/pulp_smash/settings.json``. However, there are several ways to
    alter this path. Pulp Smash obeys the `XDG Base Directory Specification`_.
    In addition, Pulp Smash responds to the ``PULP_SMASH_CONFIG_FILE``
    environment variable. This variable is a relative path, and it defaults to
    ``settings.json``.

    Configuration files contain JSON data structured in a way that resembles
    what is accepted by this class's constructor. For exact details on the
    structure of configuration files, see
    :data:`pulp_smash.config.JSON_CONFIG_SCHEMA`.

    :param pulp_auth: A two-tuple. Credentials to use when communicating with
        the server. For example: ``('username', 'password')``.
    :param pulp_version: A string, such as '1.2' or '0.8.rc3'. If you are
        unsure what to pass, consider passing '1!0' (epoch 1, version 0). Must
        be compatible with the `packaging`_ library's
        ``packaging.version.Version`` class.
    :param pulp_selinux_enabled: A boolean. Determines whether selinux tests
        are enabled.
    :param aiohttp_fixtures_origin: A string. Determines the origin where
        aiohttp fixtures can be found.
    :param hosts: A list of the hosts comprising a Pulp application. Each
        element of the list should be a :class:`pulp_smash.config.PulpHost`
        object.

    .. _packaging: https://packaging.pypa.io/en/latest/
    .. _XDG Base Directory Specification:
        http://standards.freedesktop.org/basedir-spec/basedir-spec-latest.html
    """

    def __init__(
        self,
        pulp_auth,
        pulp_version,
        pulp_selinux_enabled,
        timeout,
        aiohttp_fixtures_origin,
        *,
        hosts,
        custom=None,
    ):
        """Initialize this object with needed instance attributes."""
        self.pulp_auth = pulp_auth
        self.pulp_version = Version(pulp_version)
        self.pulp_selinux_enabled = pulp_selinux_enabled
        self.timeout = timeout
        self.aiohttp_fixtures_origin = aiohttp_fixtures_origin
        self.hosts = hosts
        self.custom = custom

    def __repr__(self):
        """Create string representation of the object."""
        attrs = _public_attrs(self)
        attrs["pulp_version"] = str(attrs["pulp_version"])
        str_kwargs = ", ".join("{}={}".format(key, repr(value)) for key, value in attrs.items())
        return "{}({})".format(type(self).__name__, str_kwargs)

    def get_hosts(self, role):
        """Return a list of hosts fulfilling the given role.

        :param role: The role to filter the available hosts, see
            `pulp_smash.config.P2_ROLES` for more information.
        """
        roles = P3_ROLES
        if role not in roles:
            raise ValueError(
                """The given role, {}, is not recognized. Valid roles are:
                {}""".format(
                    role, roles
                )
            )

        return [host for host in self.hosts if role in host.roles]

    def get_base_url(self, pulp_host=None, role="api"):
        """Generate the base URL for a given ``pulp_host``.

        :param pulp_smash.config.PulpHost pulp_host: One of the hosts that
            comprises a Pulp application. Defaults to the first host with the
            given role.
        :param role: The host role. Defaults to ``api``.
        """
        pulp_host = pulp_host or self.get_hosts(role)[0]
        scheme = pulp_host.roles[role]["scheme"]
        netloc = pulp_host.hostname
        try:
            netloc += ":" + str(pulp_host.roles[role]["port"])
        except KeyError:
            pass
        return urlunsplit((scheme, netloc, "", "", ""))

    def get_fixtures_url(self):
        """Return fixtures URL."""
        fixtures_origin = self.custom.get("fixtures_origin", PULP_FIXTURES_BASE_URL)
        return fixtures_origin

    def get_content_host(self):
        """Return content host if defined else returns api host."""
        try:
            return self.get_hosts("content")[0]
        except IndexError:
            return self.get_hosts("api")[0]

    def get_content_host_base_url(self):
        """Return content host url if defined else returns api base url."""
        pulp_host = self.get_content_host()
        return self.get_base_url(
            pulp_host=pulp_host,
            role="content" in pulp_host.roles and "content" or "api",
        )

    def get_bindings_config(self):
        """Return bindings settings."""
        configuration = Configuration(
            host=self.get_base_url(),
            username=self.pulp_auth[0],
            password=self.pulp_auth[1],
        )
        configuration.safe_chars_for_path_param = "/"
        return configuration

    def get_requests_kwargs(self, pulp_host=None):
        """Get kwargs for use by the Requests functions.

        This method returns a dict of attributes that can be unpacked and used
        as kwargs via the ``**`` operator. For example:

        >>> cfg = PulpSmashConfig.load()
        >>> requests.get(cfg.get_base_url() + '…', **cfg.get_requests_kwargs())

        This method is useful because client code may not know which attributes
        should be passed from a ``PulpSmashConfig`` object to Requests.
        Consider that the example above could also be written like this:

        >>> cfg = PulpSmashConfig.load()
        >>> requests.get(
        ...     cfg.get_base_url() + '…',
        ...     auth=tuple(cfg.pulp_auth),
        ...     verify=cfg.get_hosts('api')[0].roles['api']['verify'],
        ... )

        But this latter approach is more fragile. The user must remember to get
        a host with api role to check for the verify config, then convert
        ``pulp_auth`` config to a tuple, and it will require maintenance if
        ``cfg`` gains or loses attributes.
        """
        if not pulp_host:
            pulp_host = self.get_hosts("api")[0]
        kwargs = deepcopy(pulp_host.roles["api"])
        kwargs["auth"] = aiohttp.BasicAuth(*self.pulp_auth)
        for key in ("port", "scheme", "service"):
            kwargs.pop(key, None)
        return kwargs

    @classmethod
    def load(cls, xdg_subdir=None, config_file=None):
        """Load a configuration file from disk.

        :param xdg_subdir: Passed to :meth:`get_load_path`.
        :param config_file: Passed to :meth:`get_load_path`.
        :returns: A new :class:`pulp_smash.config.PulpSmashConfig` object. The
            current object is not modified by this method.
        :rtype: PulpSmashConfig
        """
        # Load JSON from disk.
        path = cls.get_load_path(xdg_subdir, config_file)
        with open(path) as handle:
            loaded_config = json.load(handle)

        # Make arguments.
        pulp = loaded_config.get("pulp", {})
        pulp_auth = pulp.get("auth", ["admin", "admin"])
        pulp_version = pulp.get("version", "1!0")
        pulp_selinux_enabled = pulp.get("selinux enabled", True)
        aiohttp_fixtures_origin = pulp.get("aiohttp_fixtures_origin", "127.0.0.1")
        if "systems" in loaded_config:
            warnings.warn(
                (
                    "The Pulp Smash configuration file should use a key named "
                    '"hosts," not "systems." Please update accordingly, and '
                    "validate the changes with `pulp-smash settings validate`."
                ),
                DeprecationWarning,
            )
            loaded_config["hosts"] = loaded_config.pop("systems")

        timeout = loaded_config.get("general", {}).get("timeout", 1800)

        hosts = [PulpHost(**host) for host in loaded_config.get("hosts", [])]

        custom = loaded_config.get("custom", {})

        # Make object.
        return PulpSmashConfig(
            pulp_auth,
            pulp_version,
            pulp_selinux_enabled,
            timeout,
            aiohttp_fixtures_origin,
            hosts=hosts,
            custom=custom,
        )

    @classmethod
    def get_load_path(cls, xdg_subdir=None, config_file=None):
        """Return the path to where a configuration file may be loaded from.

        Search each of the ``$XDG_CONFIG_DIRS`` for a file named
        ``$xdg_subdir/$config_file``.

        :param xdg_subdir: A string. The directory to append to each of the
            ``$XDG_CONFIG_DIRS``. Defaults to ``'pulp_smash'``.
        :param config_file: A string. The name of the settings file. Typically
            defaults to ``'settings.json'``.
        :returns: A string. The path to a configuration file, if one is found.
        :raises pulp_smash.exceptions.ConfigFileNotFoundError: If no
            configuration file is found.
        """
        if xdg_subdir is None:
            xdg_subdir = cls._get_xdg_subdir()
        if config_file is None:
            config_file = cls._get_config_file()

        for dir_ in BaseDirectory.load_config_paths(xdg_subdir):
            path = os.path.join(dir_, config_file)
            if os.path.exists(path):
                return path

        raise RuntimeError(
            "Pulp Smash is unable to find a configuration file. The "
            "following (XDG compliant) paths have been searched: "
            ", ".join(
                (
                    os.path.join(xdg_config_dir, xdg_subdir, config_file)
                    for xdg_config_dir in BaseDirectory.xdg_config_dirs
                )
            )
        )

    @staticmethod
    def _get_xdg_subdir():
        return "tests"

    @staticmethod
    def _get_config_file():
        return "settings.json"
