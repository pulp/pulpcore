"""
Helpers for in-code A/B performance experiments.

An experiment keeps the current implementation as variant A (control) and a
candidate as variant B. On each call, exactly one variant is picked at random
by a configured probability, timed, and logged. Only one variant runs per call
so the two implementations never warm each other's buffer cache.
"""

import json
import logging
import random
import time

logger = logging.getLogger("pulp.experiment")


def run_experiment(exp_id, control, candidate, *, p_candidate=0.5, correlation_id=None):
    """Run one variant of an A/B experiment and log its runtime.

    control and candidate are zero-argument callables that return the same data.
    p_candidate is the probability of running the candidate (B). Default is 0.5.
    """
    variant = "B" if random.random() < p_candidate else "A"
    func = candidate if variant == "B" else control

    start = time.monotonic()
    result = func()
    duration_ms = (time.monotonic() - start) * 1000

    logger.info(json.dumps({
        "event": "ab_experiment",
        "exp_id": exp_id,
        "variant": variant,
        "duration_ms": round(duration_ms, 3),
        "correlation_id": correlation_id,
    }))
    return result
