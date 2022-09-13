import collections
import json

import plumbum

from functools import partialmethod
from urllib.parse import urlsplit, urlunsplit


def code_handler(completed_proc):
    """Check the process for a non-zero return code. Return the process.
    Check the return code by calling ``completed_proc.check_returncode()``.
    See: :meth:`pulp_smash.cli.CompletedProcess.check_returncode`.
    """
    completed_proc.check_returncode()
    return completed_proc


class CalledProcessError(Exception):
    """Indicates a CLI process has a non-zero return code.
    See :meth:`pulp_smash.cli.CompletedProcess` for more information.
    """

    def __init__(self, args_, returncode, stdout, stderr, *args, **kwargs):
        """Require that information about the error be provided."""
        super().__init__(args_, returncode, stdout, stderr, *args, **kwargs)
        self.args_ = args_
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr

    def __str__(self):
        """Provide a human-friendly string representation of this exception."""
        return ("Command {} returned non-zero exit status {}.\n\nstdout: {}\n\nstderr: {}").format(
            self.args_, self.returncode, self.stdout, self.stderr
        )


class NoRegistryClientError(Exception):
    """We cannot determine the registry client used by a system.
    A "registry client" is a tool such as ``podman`` or ``docker``.
    """


class CompletedProcess:
    # pylint:disable=too-few-public-methods
    """A process that has finished running.
    This class is similar to the ``subprocess.CompletedProcess`` class
    available in Python 3.5 and above. Significant differences include the
    following:
    * All constructor arguments are required.
    * :meth:`check_returncode` returns a custom exception, not
      ``subprocess.CalledProcessError``.
    All constructor arguments are stored as instance attributes.
    :param args: A string or a sequence. The arguments passed to
        :meth:`pulp_smash.cli.Client.run`.
    :param returncode: The integer exit code of the executed process. Negative
        for signals.
    :param stdout: The standard output of the executed process.
    :param stderr: The standard error of the executed process.
    """

    def __init__(self, args, returncode, stdout, stderr):
        """Initialize a new object."""
        self.args = args
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr

    def __repr__(self):
        """Provide an ``eval``-compatible string representation."""
        str_kwargs = ", ".join(
            [
                "args={!r}".format(self.args),
                "returncode={!r}".format(self.returncode),
                "stdout={!r}".format(self.stdout),
                "stderr={!r}".format(self.stderr),
            ]
        )
        return "{}({})".format(type(self).__name__, str_kwargs)

    def check_returncode(self):
        if self.returncode != 0:
            raise CalledProcessError(self.args, self.returncode, self.stdout, self.stderr)


class Client:  # pylint:disable=too-few-public-methods
    """A convenience object for working with CLI.

    Example usage:
    >>> from pulp_smash import cli, config
    >>> client = cli.Client(config.PulpSmashConfig.load())
    >>> response = client.run(('echo', '-n', 'foo'))
    >>> response.returncode == 0
    """

    def __init__(self, cfg, response_handler=None):
        """TODO."""
        self.response_handler = response_handler or code_handler
        self.cfg = cfg

        self._machine = plumbum.machines.local

    def __str__(self):
        """TODO."""
        client_spec = {
            "response_handler": self.response_handler,
            "cfg": repr(self.cfg),
        }
        return "<cli.Client(%s)>" % client_spec

    def run(self, args, sudo=False, **kwargs):
        """TODO."""
        kwargs.setdefault("retcode")

        if sudo:
            args = ("sudo",) + tuple(args)

        code, stdout, stderr = self._machine[args[0]].run(args[1:], **kwargs)
        completed_process = CompletedProcess(args, code, stdout, stderr)
        return self.response_handler(completed_process)


class RegistryClient:
    """A container registry client on test runner machine.
    Each instance of this class represents the registry client on a host. An
    example may help to clarify this idea:
    >>> from pulp_smash import cli, config
    >>> registry = cli.RegistryClient(config.get_config())
    >>> image = registry.pull('image_name')
    In the example above, the ``registry`` object represents the client
    on the host where pulp-smash is running the test cases.
    Upon instantiation, a :class:`RegistryClient` object talks to its target
    host and uses simple heuristics to determine which registry client is used.
    Upon instantiation, this object determines whether it is running as root.
    If not root, all commands are prefixed with "sudo".
    Please ensure that Pulp Smash can either execute commands as root
    or can successfully execute "sudo" on the localhost.
    .. note:: When running against a non-https registry the client config
        `insecure-registries` must be enabled.
    For docker it is located in `/etc/docker/daemon.json` and content is::
        {"insecure-registries": ["pulp_host:24816"]}
    For podman it is located in `/etc/containers/registries.conf` with::
        [registries.insecure]
        registries = ['pulp_host:24816']
    :param pulp_smash.config.PulpSmashConfig cfg: Information about the target
        host.
    :param tuple raise_if_unsupported: a tuple of Exception and optional
        string message to force raise_if_unsupported on initialization::
          rc = RegistryClient(cfg, (unittest.SkipTest, 'Test requires podman'))
          # will raise and skip if unsupported package manager
        The optional is calling `rc.raise_if_unsupported` explicitly.
    :param pulp_host: The host where the Registry Client will run, by default
        it is set to None and then the same machine where tests are executed
        will be assumed.
    """

    def __init__(self, cfg, raise_if_unsupported=None, pulp_host=None):
        """Initialize a new RegistryClient object."""
        if pulp_host is None:
            # to comply with Client API
            smashrunner = collections.namedtuple("Host", "hostname roles")
            smashrunner.hostname = "localhost"
            smashrunner.roles = {"shell": {"transport": "local"}}
            self._pulp_host = smashrunner
        else:
            self._pulp_host = pulp_host

        self._cfg = cfg
        self._client = Client(cfg)
        self._name = None
        if raise_if_unsupported is not None:
            self.raise_if_unsupported(*raise_if_unsupported)

    @property
    def name(self):
        """Return the name of the Registry Client."""
        if not self._name:
            self._name = self._get_registry_client()
        return self._name

    def raise_if_unsupported(self, exc, message="Unsupported registry client"):
        """Check if the registry client is supported else raise exc.
        Use case::
            rc = RegistryClient(cfg)
            rc.raise_if_unsupported(unittest.SkipTest, 'Test requires podman')
            # will raise and skip if not podman or docker
            rc.pull('busybox')
        """
        try:
            self.name
        except NoRegistryClientError:
            raise exc(message)

    def _get_registry_client(self):
        """Talk to the host and determine the registry client.
        Return "podman" or "docker" if the registry client appears to be one of
        those.
        :raises pulp_smash.exceptions.NoRegistryClientError: If unable to
        find any valid registry client on host.
        """
        client = Client(self._cfg)
        cmd = ("which", "podman")
        registry_client = "podman"
        if client.run(cmd).returncode == 0:
            return registry_client

        raise NoRegistryClientError(
            "Unable to determine the registry client used by {}. "
            "The client '{}' does not appear to be installed.".format(
                self._pulp_host.hostname, registry_client
            )
        )

    def _dispatch_command(self, command, *args):
        """Dispatch a command to the registry client."""
        # Scheme should not be part of image path, if so, remove it.
        if args and args[0].startswith(("http://", "https://")):
            args = list(args)
            args[0] = urlunsplit(urlsplit(args[0])._replace(scheme="")).strip("//")

        cmd = (self.name, command) + tuple(args)
        result = self._client.run(cmd)
        try:
            # most client responses are JSONable
            return json.loads(result.stdout)
        except Exception:  # pylint:disable=broad-except
            # Python 3.4 has no specific error for json module
            return result

    pull = partialmethod(_dispatch_command, "pull")
    """Pulls image from registry."""
    push = partialmethod(_dispatch_command, "push")
    """Pushes image to registry."""
    login = partialmethod(_dispatch_command, "login")
    """Authenticate to a registry."""
    logout = partialmethod(_dispatch_command, "logout")
    """Logs out of a registry."""
    inspect = partialmethod(_dispatch_command, "inspect")
    """Inspect metadata for pulled image."""
    import_ = partialmethod(_dispatch_command, "import")
    """Import a container as a file in to the registry."""
    images = partialmethod(_dispatch_command, "images", "--format", "json")
    """List all pulled images."""
    rmi = partialmethod(_dispatch_command, "rmi")
    """removes pulled image."""
    tag = partialmethod(_dispatch_command, "tag")
    """tags image."""
