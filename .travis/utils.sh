# This file is meant to be sourced by ci-scripts

PULP_CONTAINER=pulp

# Run a command
cmd_prefix() {
  docker exec "$PULP_CONTAINER" "$@"
}

# Run a command, and pass STDIN
cmd_stdin_prefix() {
  docker exec -i "$PULP_CONTAINER" "$@"
}
