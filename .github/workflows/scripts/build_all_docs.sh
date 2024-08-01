#!/bin/bash

# This script builds the documentation site for pulpproject.org

set -euv

pip install git+https://github.com/pulp/pulp-docs.git
pulp-docs build
tar cvf pulpproject.org.tar site
