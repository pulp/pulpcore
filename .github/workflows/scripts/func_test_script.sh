#!/usr/bin/env bash
# Functional test runner with task-queue sampling right after parallel suites.
# Sourced from script.sh via FUNC_TEST_SCRIPT.

_nightly_args=()
if [[ "${GITHUB_WORKFLOW:-}" =~ "Nightly" ]]; then
  _nightly_args=(--nightly)
fi

_pytest_common=(-v --timeout=300 -r sx --color=yes --suppress-no-test-exit-code --durations=20)

# Parallel suites first (xdist -n 8), then sample worker-queue waits before serial.
cmd_user_prefix bash -c "pytest ${_pytest_common[*]} --pyargs pulpcore.tests.functional -m parallel -n 8 ${_nightly_args[*]}"
cmd_user_prefix bash -c "pytest ${_pytest_common[*]} --pyargs pulp_file.tests.functional -m parallel -n 8 ${_nightly_args[*]}"
cmd_user_prefix bash -c "pytest ${_pytest_common[*]} --pyargs pulp_certguard.tests.functional -m parallel -n 8 ${_nightly_args[*]}"

echo "::group::Task queue wait stats (after parallel suites)"
# Short window: capture tasks from the parallel phase before purge/serial dilute the signal.
cmd_user_prefix pulpcore-manager task-queue-stats --hours 1 --top 20 || true
echo "::endgroup::"

cmd_user_prefix bash -c "pytest ${_pytest_common[*]} --pyargs pulpcore.tests.functional -m 'not parallel' ${_nightly_args[*]}"
cmd_user_prefix bash -c "pytest ${_pytest_common[*]} --pyargs pulp_file.tests.functional -m 'not parallel' ${_nightly_args[*]}"
cmd_user_prefix bash -c "pytest ${_pytest_common[*]} --pyargs pulp_certguard.tests.functional -m 'not parallel' ${_nightly_args[*]}"
