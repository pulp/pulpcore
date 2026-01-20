# Pulp Errors

When working with Pulp, you may encounter error codes during task execution.
Pulp uses error codes in the format `[PLP####]` to identify specific error conditions.

!!! info "Security: Tracebacks Are Not Returned"
    To prevent information disclosure, exception tracebacks are logged server-side but are
    NOT stored in the task or returned to API users.
    This prevents sensitive information (URLs, credentials, file paths) from being exposed through the API.

## Error Code Reference

Listed below are all available Pulp error codes, sorted numerically.

### PLP0000 - Internal Error

An unexpected internal error occurred.
This error is raised automatically by the task system for unexpected exceptions.

**Error message:** `"[PLP0000] An internal error occurred."`

**When you might see this:** Unexpected server errors (equivalent of HTTP 500).

---

### PLP0002 - Missing Plugin

A requested plugin is not installed on the server.

**Error message:** `"[PLP0002] Plugin with Django app label <name> is not installed."`

**When you might see this:** Attempting to use functionality from a plugin that is not installed.

---

### PLP0003 - Digest Validation Error

A file failed checksum validation during download or artifact validation.

**Error message:** `"[PLP0003] A file located at the url {url} failed validation due to checksum. Expected '{expected}', Actual '{actual}'"`

**When you might see this:** Downloaded files that don't match their expected checksums, indicating corruption or tampering.

---

### PLP0004 - Size Validation Error

A file failed size validation during download or artifact validation.

**Error message:** `"[PLP0004] A file located at the url {url} failed validation due to size. Expected '{expected}', Actual '{actual}'"`

**When you might see this:** Downloaded files that don't match their expected size, indicating incomplete downloads or corruption.

---

### PLP0005 - Timeout

A download or network request timed out.

**Error message:** `"[PLP0005] Request timed out for {url}. Increasing the total_timeout value on the remote might help."`

**When you might see this:** Slow or unresponsive remote servers.
You can adjust the `total_timeout` value on the remote configuration to allow more time for the request.

---

### PLP0006 - Resource Immutable

Attempted to modify an immutable resource.

**Error message:** `"[PLP0006] Cannot update immutable resource {model_pk} of type {model_type}"`

**When you might see this:** Trying to modify resources that cannot be changed once created, such as published repository versions.

---

### PLP0007 - Domain Protected

Attempted to delete a domain that still contains repositories with content.

**Error message:** `"[PLP0007] You cannot delete a domain that still contains repositories with content."`

**When you might see this:** Trying to delete a domain before cleaning up its repositories and content.
Remove all repositories with content from the domain first.

---

### PLP0008 - DNS Domain Name Error

DNS resolution failed for a URL during download operations.

**Error message:** `"[PLP0008] URL lookup failed."`

**When you might see this:** The domain name in a URL cannot be resolved to an IP address.
Check the URL and DNS configuration.

---

### PLP0009 - Unsupported URL Scheme

An unsupported URL scheme was provided.

**Error message:** `"[PLP0009] URL: {url} not supported."`

**When you might see this:** Using URL schemes that Pulp doesn't support (e.g., `ftp://` when only `http://` and `https://` are supported).

---

### PLP0010 - Proxy Authentication Error

Proxy authentication failed.

**Error message:** `"[PLP0010] Proxy authentication failed for {proxy_url}. Please check your proxy credentials."`

**When you might see this:** The proxy server returned HTTP 407, indicating authentication is required or failed.
Verify your proxy credentials are correct.

---

### PLP0011 - Repository Version Delete Error

Attempted to delete the only remaining repository version.

**Error message:** `"[PLP0011] Cannot delete repository version. Repositories must have at least one repository version."`

**When you might see this:** Trying to delete the last version of a repository.
Repositories must always have at least one version.
