set -euv

if [[ "$TEST" == "azure" ]]; then
    cmd_stdin_prefix bash -c "cat > /var/lib/pulp/scripts/otel_server.py" < "$GITHUB_WORKSPACE"/pulpcore/tests/functional/assets/otel_server.py
    docker exec -d "$PULP_CI_CONTAINER" "$@" su pulp -c "python3 /var/lib/pulp/scripts/otel_server.py"
fi
