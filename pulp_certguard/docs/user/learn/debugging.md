# Debugging

`pulp-certguard` contains debug statements which show the raw, received value of the
`X-CLIENT-CERT` header. This can be very valuable when debugging where the problem is in the chain
of certificates from the:

```
client <--> reverse proxy <--> pulp-certguard
```

## Enabling Debugging

Debugging is most easily enabled by adding the following line to your settings file, which is
by default located at `/etc/pulp/settings.py`:

```
LOGGING = {"dynaconf_merge": True, "loggers": {'': {'handlers': ['console'], 'level': 'DEBUG'}}}
```

After restarting your server-side services and making a request that sets the `X-CLIENT-CERT`
header, you should see a log message for each request where pulp-certguard is receiving a
`X-CLIENT-CERT` header.

## Using Logging Info

If you make a request but do not see a log message, you could have one of the following problems:

1. Debug logging is not enabled or applied. Check your `LOGGING` config.
2. The client is not requesting content from a Distribution protected with `pulp-certguard`. Check
   your `Distribution` configuration.
3. The reverse proxy isn't configured to pass along the `X-CLIENT-CERT` config correctly. Check
   your reverse proxy config against the example configs documented on this site.

If you do see a log message, but it's still not working you could have one of the following
problems:

1. The client isn't submitting the client certificate correctly to the reverse proxy. Ensure the
   client is submitting a certificate and key via TLS to the reverse proxy.
2. The reverse proxy configuration is not correct. Compare your reverse proxy config against the
   example configs documented on this site.

## Checking Authorized URLs in RHSM Certificates

The `rct cat-crt` command is useful for printing the detailed contents of RHSM certificates. This
is typically provided by the `subscription-manager` rpm on Centos, Fedora, and RHEL systems.

Once installed you can show the contents of an RHSM cert like this example running on a
[test certificate](https://github.com/pulp/pulp-certguard/blob/master/pulp_certguard/tests/functional/artifacts/rhsm/v3/4260035510644027985.pem):

```
$ rct cat-cert 4260035510644027985.pem

+-------------------------------------------+
        Entitlement Certificate
+-------------------------------------------+

Certificate:
        Path: v3/4260035510644027985.pem
        Version: 3.4
        Serial: 4260035510644027985
        Start Date: 2020-03-05 19:50:59+00:00
        End Date: 2048-06-01 00:00:00+00:00
        Pool ID: Not Available

Subject:
        CN: d3c3ff52c107457dbd3a0c28a345754a
        O: Default_Organization

Issuer:
        C: US
        CN: sat-6-6-qa-rhel7.windhelm.example.com
        L: Raleigh
        O: Katello
        OU: SomeOrgUnit
        ST: North Carolina



Authorized Content URLs:
        /Default_Organization/Library/custom/foo/foo
```
