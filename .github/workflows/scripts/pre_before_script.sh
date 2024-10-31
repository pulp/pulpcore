set -euv

if [ "$TEST" = "azure" ]; then
    cmd_stdin_prefix bash -c "cat > /etc/nginx/pulp/api_root_rewrite.conf" < pulpcore/tests/functional/assets/api_root_rewrite.conf
    cmd_prefix bash -c "s6-rc -d change nginx"
    cmd_prefix bash -c "s6-rc -u change nginx"
    # it is necessary to wait for a short period until the service starts; otherwise, any subsequent requests to Pulp's API endpoints will fail
    sleep 1
fi
