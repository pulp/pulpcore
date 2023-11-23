set -euv



if [ "$TEST" = "azure" ]; then
    cmd_stdin_prefix bash -c "cat > /var/lib/pulp/scripts/otel_server.py" < pulpcore/tests/functional/assets/otel_server.py
    cmd_user_prefix nohup python3 /var/lib/pulp/scripts/otel_server.py &
fi
