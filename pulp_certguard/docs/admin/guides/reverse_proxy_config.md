# Reverse Proxy Config

The client certificate submitted terminates [Transport Layer Security](https://en.wikipedia.org/wiki/Transport_Layer_Security) (TLS) at the reverse proxy. The reverse proxy must do two things to
correctly pass the client certificate to the `pulpcore-content` app.

1. Forward the client's TLS certificate as the `X-CLIENT-CERT`.
2. The `X-CLIENT-CERT` needs to be urlencoded.

## Nginx Config Example

To configure Nginx to accept a client cert, and have it forward the urlencoded cert:

1. Enable the checking of a client cert with the  [ssl_verify_client directive](https://nginx.org/en/docs/http/ngx_http_ssl_module.html#ssl_verify_client).

2. Configure the `X-CLIENT-CERT` header to be urlencoded and forwarded. To avoid a client
   falsifying the header, first unset it. It forwards the [\$ssl_client_escaped_cert](https://nginx.org/en/docs/http/ngx_http_ssl_module.html#var_ssl_client_escaped_cert) variable
   which is the urlencoded client cert:

   ```
   proxy_set_header X-CLIENT-CERT $ssl_client_escaped_cert;
   ```

## Apache 2.4.10+ Config Example

To configure Apache to accept a client cert, urlencode it, and forward it you will need to:

1. Enable the checking of a client cert with the [SSLVerifyClient directive](https://httpd.apache.org/docs/current/mod/mod_ssl.html#sslverifyclient).

2. Enable the client certificate to be available as an environment variable with:

   ```
   SSLOptions +ExportCertData
   ```

3. Configure the `X-CLIENT-CERT` header to be urlencoded and forwarded. To avoid a client
   falsifying the header, first unset it. Then use [mod_rewrite](https://httpd.apache.org/docs/current/mod/mod_rewrite.html) to urlencode the [SSL_CLIENT_CERT](https://httpd.apache.org/docs/2.4/mod/mod_ssl.html) environment variable as follows:

   ```
   RequestHeader unset X-CLIENT-CERT
   RequestHeader set X-CLIENT-CERT "expr=%{escape:%{SSL_CLIENT_CERT}s}"
   ```

## Apache \< 2.4.10 Config Example

Apache versions earlier than 2.4.10 are not able to urlencode the client certificate.
`pulp-certguard` tries to detect this situation and work anyway.

In this case, to configure Apache to accept a client cert and forward it you will need to:

1. Enable the checking of a client cert with the [SSLVerifyClient directive](https://httpd.apache.org/docs/current/mod/mod_ssl.html#sslverifyclient).

2. Enable the client certificate to be available as an environment variable with:

   ```
   SSLOptions +ExportCertData
   ```

3. Configure the `X-CLIENT-CERT` header to be forwarded. To avoid a client falsifying the header,
   first unset it, then forward the data in the [SSL_CLIENT_CERT](https://httpd.apache.org/docs/2.4/mod/mod_ssl.html) environment variable as follows:

   ```
   RequestHeader unset X-CLIENT-CERT
   RequestHeader set X-CLIENT-CERT "%{SSL_CLIENT_CERT}s"
   ```
