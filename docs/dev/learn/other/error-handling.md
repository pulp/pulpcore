# Error Handling

## Errors in Tasks

All uncaught exceptions in a task are treated as fatal exceptions and the task is marked as failed.
The error description and error code are stored in the `error` attribute of the `pulpcore.app.models.Task` object and returned to the user.

!!! warning "Security: Tracebacks Are Not Returned"
    To prevent information disclosure, **exception tracebacks are logged server-side but are
    NOT stored in the task or returned to API users**.
    This prevents sensitive information (URLs, credentials, file paths) from being exposed through the API.

## Exception Types

### Standard Python Exceptions

For programming errors and standard error scenarios, use [built-in Python exceptions](https://docs.python.org/3/library/exceptions.html)
(e.g., `ValueError`, `TypeError`, `KeyError`).
These are appropriate for logic errors and invalid inputs.

### PulpException - Base Class for Domain Errors

For known Pulp-specific error scenarios (timeouts, authentication failures, validation errors),
use exceptions that inherit from `pulpcore.exceptions.PulpException`.
Each PulpException:

- Has a unique **error code** (e.g., `PLP0005`)
- Has an associated **HTTP status code** (defaults to 500)
- Implements a user-safe `__str__()` method that includes the error code in `[PLP####]` format followed by a description without sensitive data

When a `PulpException` is raised in a task, the error message (including the error code) and description are returned to the user.
Tracebacks are logged but never exposed through the API.

!!! note "Error Code Reference"
    For a complete list of all Pulp error codes and their meanings, see the [Pulp Errors](site:pulpcore/docs/user/reference/pulp-errors/) user documentation.

## Using PulpException in Code

Below are implementation examples for the available PulpExceptions.

### PLP0000 - InternalErrorException

Signals an unexpected internal error.
This is raised automatically by the task system when an uncaught exception occurs that is not a `PulpException`.

**Usage in code:**
```python
safe_exc = InternalErrorException()
task.set_failed(safe_exc)
```

**When used:** Automatically raised by the task system for unexpected errors (equivalent of HTTP 500).

---

### PLP0002 - MissingPlugin

Raised when a requested plugin is not installed.

**Usage in code:**
```python
raise MissingPlugin(plugin_app_label)
```

---

### PLP0003 - DigestValidationError

Raised when a file fails digest/checksum validation during download or artifact validation.

**Usage in code:**
```python
raise DigestValidationError(actual_digest, expected_digest, url=self.url)
```

---

### PLP0004 - SizeValidationError

Raised when a file fails size validation during download or artifact validation.

**Usage in code:**
```python
raise SizeValidationError(actual_size, expected_size, url=self.url)
```

---

### PLP0005 - TimeoutException

Raised when a download or network request times out.

**Usage in code:**
```python
raise TimeoutException(self.url)
```

---

### PLP0006 - ResourceImmutableError

Raised when attempting to modify an immutable resource (e.g., a published repository version).

**Usage in code:**
```python
raise ResourceImmutableError(self)
```

---

### PLP0007 - DomainProtectedError

Raised when attempting to delete a domain that still contains repositories with content.

**Usage in code:**
```python
raise DomainProtectedError()
```

---

### PLP0008 - DnsDomainNameException

Raised when DNS resolution fails for a URL during download operations.

**Usage in code:**
```python
raise DnsDomainNameException(self.url)
```

---

### PLP0009 - UrlSchemeNotSupportedError

Raised when an unsupported URL scheme is provided (e.g., `ftp://` when only `http://` and `https://` are supported).

**Usage in code:**
```python
raise UrlSchemeNotSupportedError(url)
```

---

### PLP0010 - ProxyAuthenticationError

Raised when proxy authentication fails (HTTP 407 response from proxy server).

**Usage in code:**
```python
raise ProxyAuthenticationError(self.proxy)
```

---

### PLP0011 - RepositoryVersionDeleteError

Raised when attempting to delete a repository version when it's the only version remaining.

**Usage in code:**
```python
raise RepositoryVersionDeleteError()
```
