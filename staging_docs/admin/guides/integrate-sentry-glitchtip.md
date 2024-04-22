# Integrate with Sentry or GlitchTip

Pulp can be configured to report unhandled exceptions to Sentry or GlitchTip.
All unhandled exceptions in `pulpcore-api` and `pulpcore-content` are reported to GlitchTip.
Exceptions encountered during task execution are not reported to GlitchTip.
Tasks API should be used to view exceptions encountered during task execution.

1. Install the `sentry-sdk` package.
2. Set the `SENTRY_DSN` environment variable to configure where to report the exceptions.
