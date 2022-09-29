# This file is meant to be sourced by ci-scripts

# WARNING: DO NOT EDIT!
#
# This file was generated by plugin_template, and is managed by it. Please use
# './plugin-template --github pulpcore' to update this file.
#
# For more info visit https://github.com/pulp/plugin_template

# Run a command
alias cmd_prefix='docker exec pulp'

# Run a command as the limited pulp user
alias cmd_user_prefix='docker exec -u pulp pulp'

# Run a command, and pass STDIN
alias cmd_stdin_prefix='docker exec -i pulp'

# Run a command as the lmited pulp user, and pass STDIN
alias cmd_user_stdin_prefix='docker exec -i -u pulp pulp'
