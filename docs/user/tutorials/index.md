# Start Here

If you are a new user and are unsure where to begin, this page outlines the different options available, as well as the limitations and requirements for those options.

## Want to evaluate Pulp?

The quickest way to evaluate Pulp is by using Pulp in One Container.
This image contains all the services that you need to run Pulp and is perfect for an initial evaluation.
Mind that this container cannot scale to provide for high availability scenarios.

For installation instructions, see
[Pulp in One Container](site:pulp-oci-images/docs/admin/tutorials/quickstart/).

## Is there a Kubernetes/OpenShift deployment option?

Pulp operator endeavours to provide a scalable and robust cluster for Pulp 3.
Pulp can be installed from [OperatorHub](https://operatorhub.io/operator/pulp-operator).
If you're interested in providing feedback or contributing to making this better, see the
[Pulp operator repo](https://github.com/pulp/pulp-operator) on GitHub.

For more information about using Pulp operator, see
[Pulp on Openshift](site:pulp-operator/docs/admin/tutorials/quickstart-openshift/)

## Is there a podman/docker compose deployment option?

Based on community feedback from the survey and PulpCon 2021, we have reused the Pulp operator images to create a podman compose option for deploying Pulp.
If you're familiar with podman compose, you can customize the configuration to suit your deployment needs and to deploy at scale.

For more information see our
[podman/docker compose intro section](site:pulp-oci-images/docs/admin/tutorials/quickstart/#podman-or-docker-compose).

## Do you need something else?

If you are blocked and don't find an option that you need, please post to our [Pulp Community Discourse](https://discourse.pulpproject.org) and let us know what problem you encountered or what scenario you're missing. Feel free to introduce yourself, what you're trying to achieve, where you ran into problems or didn't understand something. We're always happy to hear how people are using Pulp!

You can also find us on [**pulp** on Matrix](https://matrix.to/#/!HWvLQmBGVPfJfTQBAu:matrix.org) for user support.

!!! note

    We plan to write an Introduction Tutorial to teach fundamentals skills and concepts throught a basic Project.
    Reach out if you have a good idea of what this didactical Project could look like.

