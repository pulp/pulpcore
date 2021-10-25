SigningService scripts can now access the public key fingerprint using the ``PULP_SIGNING_KEY_FINGERPRINT`` environment variable.
This allows for more generic scripts, that do not need to "guess" (hardcode) what key they should use.
