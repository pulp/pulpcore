#!/bin/bash

set -euv

# # See pulpcore.app.util.ENABLE_6064_BACKPORT_WORKAROUND for context.
# This needs to be set here because it relies on service init.
# Its being tested in only one scenario to have both cases covered.
if [[ "$TEST" == "s3" ]]; then
    cmd_prefix pulpcore-manager backport-patch-6064
fi

