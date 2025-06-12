#!/bin/bash

# This script builds the documentation site for pulpproject.org

set -euv

FETCHDIR="/tmp/fetchdir"
pip install git+https://github.com/pulp/pulp-docs.git
pulp-docs fetch --dest "$FETCHDIR"
pulp-docs build --path "$FETCHDIR"
tar cvf pulpproject.org.tar site
