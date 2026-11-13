"""Helpers for evaluating user-supplied jq filters safely."""

import jq


def compile_safe_jq(program):
    """
    Compile a user-supplied jq filter with the process environment hidden.

    jq exposes the environment of the running process through the `env`
    builtin and the `$ENV` variable. Filters may come from untrusted sources,
    such as a content guard created by a domain administrator, so evaluating
    them as-is can leak secrets held in the environment of the process, e.g. the
    Django `SECRET_KEY` or the database password.

    Shadowing both interfaces keeps the rest of the jq language available while
    making the environment unreachable from the filter.
    """
    return jq.compile(f"def env: {{}}; {{}} as $ENV | ({program}\n)")
