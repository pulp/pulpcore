#!/usr/bin/env bash
# Run after functional tests to report task worker-queue waits.
#
# Uses pulpcore-manager task-queue-stats. Safe to no-op on Redis worker
# scenarios (command prints a warning; stats may be empty/unreliable).

set -euo pipefail

# make sure this script runs at the repo root when sourced from script.sh
cd "$(dirname "$(realpath -e "$0")")"/../../..

source .github/workflows/scripts/utils.sh

echo "::group::Task queue wait stats"
cmd_user_prefix pulpcore-manager task-queue-stats --hours 6 --top 20 || true
echo "::endgroup::"
