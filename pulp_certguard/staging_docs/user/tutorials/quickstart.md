# Quickstart

To meaningfully use pulp-certguard you should already have a Pulp Distribution that requires
authorization and ideally it should have content in it. These examples assume you have a [pulp_file](site:/pulp_file/)
`FileRepository` with at least one `RepositoryVersion` with content in it. Also you'll need a `FileDistribution` serving that
`RepositoryVersion`.

The pulp-certguard examples should be straightforward to port to protect another distribution type.

### Create content to be protected

This step is about creating some data to test with. The significant thing for pulp-certguard is
having a repository to protect and having some content in that repository to test against.
```bash
echo "Creating FileRemote..."
pulp file remote create \
  --name certguard-remote \
  --url "https://fixtures.pulpproject.org/file/PULP_MANIFEST" \
  --policy on_demand
echo "Creating FileRepository..."
pulp file repository create \
  --name certguard-repository \
  --remote certguard-remote \
  --autopublish
echo "Sync repository..."
pulp file repository sync  \
  --name certguard-repository
echo "Distribute the respoitory's content..."
pulp file distribution create \
  --name certguard-distribution \
  --repository file:file:certguard-repository \
  --base-path file/certguard-repository
```

## X509 CertGuard

### Create a content guard

This example assumes that `./ca.pem` is a PEM encoded Certificate Authority (CA) certificate. Each
X509 Content Guard needs a name so for this example we'll use `myguard`.

=== "Create X509 ContentGuard"

    ```bash
    pulp content-guard x509 create \
      --name my-509-guard \
      --ca-certificate=@./ca.pem
    ```

=== "Create RHSM ContentGuard"

    ```bash
    pulp content-guard rhsm create \
      --name my-rhsm-guard \
      --ca-certificate=@./ca.pem
    ```

=== "X509 Output"

    ```json
    {
      "pulp_href": "/pulp/api/v3/contentguards/certguard/x509/018dbdce-83c8-7602-ae8f-e8d5262d3cb8/",
      "pulp_created": "2024-02-18T20:00:44.489636Z",
      "name": "my-509-guard",
      "description": null,
      "ca_certificate": "-----BEGIN CERTIFICATE-----\n...-----END CERTIFICATE-----"
    }
    ```

=== "RHSM Output"

    ```json
    {
      "pulp_href": "/pulp/api/v3/contentguards/certguard/rhsm/018dbddd-1894-7658-ab8f-1f33b544f2fc/",
      "pulp_created": "2024-02-18T20:16:40.085402Z",
      "name": "my-rhsm-guard",
      "description": null,
      "ca_certificate": "-----BEGIN CERTIFICATE-----\n...-----END CERTIFICATE-----"
    }
    ```

### Protect the Distribution with the X509CertGuard

=== "Associate a ContentGuard to a Repository"

    ```bash
    pulp file distribution update \
      --name certguard-distribution \
      --content-guard certguard:x509:my-509-guard
    ```

=== "Output"

    ```console
    Started background task /pulp/api/v3/tasks/018dbdd6-ec6e-7cd9-a49d-1c1a2e55725f/
    Done.
    ```

### Download `protected` content

#### X509 and RHSM Certguards

The following example assume the client will connect to the reverse proxy using TLS with the
following:

- The PEM encoded client certificate is stored at `~/client.pem` which is signed by the CA stored
  on the X509CertGuard.
- The corresponding PEM encoded private key at `~/key.pem`.

It attempts to download the `1.iso` file from the FileDistribution at the path
`/pulp/content/somepath/` Note the `somepath` part of this is from the `base_url` of the
Distribution you are testing against.

For example with httpie you can submit the client cert and key via TLS using:

```bash
$ http --cert ~/client.pem --cert-key ~/key.pem https://localhost/pulp/content/somepath/test.iso`
```

This is expected to yield binary data with a response like:

```console
HTTP/1.1 200 OK
Accept-Ranges: bytes
Connection: keep-alive
Content-Length: 3145728
Content-Type: application/octet-stream
Date: Tue, 21 Apr 2020 20:35:11 GMT
Last-Modified: Tue, 21 Apr 2020 19:23:06 GMT
Server: nginx/1.16.1



+-----------------------------------------+
| NOTE: binary data not shown in terminal |
+-----------------------------------------+
```

## RHSM-CertGuard-specific rules

!!! note
    To use the `RHSMCertGuard` you have to manually install the [rhsm Python module](https://pypi.org/project/rhsm/) which provides RHSM certificate parsing on the pulp server.
    It requires some system level dependencies, e.g. OpenSSL libraries, which are not the same on
    all operating operating systems. `rhsm` from PyPI not being cross-distro is why this requires
    manual installation.


If the RHSM client cert contains entitlement paths, **they must match the full path to the
Distribution** the client is fetching from. In this example that is `/pulp/content/somepath/`.


