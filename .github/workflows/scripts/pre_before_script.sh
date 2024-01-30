set -euv

if [ "$TEST" = "azure" ]; then
    cmd_stdin_prefix bash -c "cat > /etc/nginx/pulp/api_root_rewrite.conf" < pulpcore/tests/functional/assets/api_root_rewrite.conf
    cmd_prefix bash -c "s6-rc -d change nginx"
    cmd_prefix bash -c "s6-rc -u change nginx"
    cmd_stdin_prefix bash -c "cat > /var/lib/pulp/scripts/otel_server.py" < pulpcore/tests/functional/assets/otel_server.py
    cmd_user_prefix nohup python3 /var/lib/pulp/scripts/otel_server.py &
fi
