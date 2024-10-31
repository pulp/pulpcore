set -euv

if [ "$TEST" = "azure" ]; then
    cmd_stdin_prefix bash -c "cat > /etc/nginx/pulp/api_root_rewrite.conf" < pulpcore/tests/functional/assets/api_root_rewrite.conf
    cmd_prefix bash -c "s6-rc -d change nginx"
    cmd_prefix bash -c "s6-rc -u change nginx"
    cmd_prefix bash -c "until s6-svstat /var/run/service/nginx | grep -q \"up\"; do sleep 1; done"
fi
