# Integrate Kafka

Pulp can be configured to emit messages as tasks are created and executed.

Kafka configuration depends on how the kafka broker is configured. Which settings are applicable depends on the broker
configuration.

For a development preview of this functionality, the kafka profile from
[oci_env](https://github.com/pulp/oci_env/pull/159) can be used:

```
COMPOSE_PROFILE=kafka
```

After triggering task(s) any kafka consumer can be used to explore the resulting messages. 
For convenience, the previously mentioned `oci_env` setup contains a CLI consumer that can be invoked as follows:

```shell
oci-env exec -s kafka \
  /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server=localhost:9092 \
  --offset earliest \
  --partition 0 \
  --topic pulpcore.tasking.status \
  --max-messages 1
```

## Common Configuration

`KAFKA_BOOTSTRAP_SERVERS` is a comma-separated list of hostname and port pairs. Setting this enables the kafka
integration.

Example values:

- `localhost:9092`
- `kafka1.example.com:9092,kafka2.example.com:9092`
 
## Authentication: Username/Password

In order to use username/password authentication, it's necessary to set an appropriate `KAFKA_SECURITY_PROTOCOL` value:

- `sasl_ssl` when the connection uses TLS. 
- `sasl_plaintext` when the connection does not use TLS.

It's also necessary to set the appropriate value for `KAFKA_SASL_MECHANISM`; consult kafka broker configuration, typical
values include:

- `SCRAM-SHA-256`
- `SCRAM-SHA-512`

## TLS Settings

If the TLS truststore needs to be customized, then `KAFKA_SSL_CA_PEM` can be used to provide CA certs in PEM format.

!!! note
    The pulp kafka integration does not currently expose settings necessary for mTLS (client certificates).

## Other settings

See [Kafka Settings](../reference/settings.md#kafka-settings) for details.