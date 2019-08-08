# Pulp 3 Containers

This directory contains assets and tooling for building Pulp 3 container images.

The image names differ based on the set of plugins installed, including none (pulpcore-plugin only). The image tags differ based on the versions of pulpcore & the plugins.

Each image is an all-in-one image that gets called with different commands to assume each of the roles. The roles must be specified as the container's "command", without the full filepath:

* pulp-api
* pulp-content
* pulp-worker
* pulp-resource-manager

The single entrypoint script (which is aware of the command string) should help keep the commands as stable interfaces.

## Build

The images can be built with the help of an Ansible playbook. To build the images:

    ansible-playbook build.yaml

See `vars/defaults.yaml` for how to customize the "images" variable (data structure.)

WARNING: Due to a limitation of Docker (but not Podman), Docker will copy the entire parent directory of "pulpcore" during build (the "build context.") This could slow your system down, exhaust disk space, or copy sensitive data you do not want copied. If using Docker, you probably want to clone pulpcore into a new parent directory, or one with the other pulp repos under it.

## Push Image to Registry

The built image can be pushed to a registry using an Ansible playbook. The default configuration will attempt to push the images to `quay.io/pulp`:

    ansible-playbook push.yaml

The image can be pushed to custom registry by specifying variables via the command line:

    ansible-playbook push.yaml -e registry=docker.io -e project=myproject

See `vars/defaults.yaml` for more info about the variables.
