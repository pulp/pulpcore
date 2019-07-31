# Pulp 3 Containers

This directory contains assets and tooling for building Pulp 3 container images. The images differ based on the set of plugins installed, including none (pulpcore-plugin only.) Each image is an all-in-one image that gets called with different commands to assume each of the roles. The roles must be specified as the container's "command", without the full filepath:

* pulp-api
* pulp-content
* pulp-worker
* pulp-resource-manager

The single entrypoint script (which is aware of the command string) should help keep the commands as stable interfaces.

## Build

The images can be built with the help of an Ansible playbook. To build the images:

    ansible-playbook build.yaml

The variable "images" can be overriden. It includes specifying the plugins per image.

The default value (yaml converted to json):

    ansible-playbook build.yaml -e '{"images":[{"pulpcore":{"plugins":["pulpcore-plugin"]}},{"pulp":{"plugins":["pulp-file","pulp-ansible","pulp-cookbook","pulp-docker","pulp-maven","pulp-python","pulp-rpm"]}}]}'

The default value, but with nightly versions of plugins instead:

    ansible-playbook build.yaml -e '{"images":[{"pulpcore":{"plugins":["git+https://github.com/pulp/pulpcore-plugin.git"]}},{"pulp":{"plugins":["git+https://github.com/pulp/pulp_file.git","git+https://github.com/pulp/pulp_ansible.git","git+https://github.com/gmbnomis/pulp_cookbook.git","git+https://github.com/pulp/pulp_docker.git","git+https://github.com/pulp/pulp_maven.git","git+https://github.com/pulp/pulp_python.git","git+https://github.com/pulp/pulp_rpm.git"]}}]}'

## Push Image to Registry

The built image can be pushed to a registry using an Ansible playbook. The default configuration will attempt to push the image to `quay.io/pulp`:

    ansible-playbook push.yaml

The image can be pushed to custom registry by specifying variables via the command line:

    ansible-playbook push.yaml -e registry=docker.io -e project=myproject
