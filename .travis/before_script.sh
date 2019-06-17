#!/usr/bin/env sh
set -v

export PRE_BEFORE_SCRIPT=$TRAVIS_BUILD_DIR/.travis/pre_before_script.sh
export POST_BEFORE_SCRIPT=$TRAVIS_BUILD_DIR/.travis/post_before_script.sh

if [ -f $PRE_BEFORE_SCRIPT ]; then
    $PRE_BEFORE_SCRIPT
fi


mkdir -p ~/.config/pulp_smash
cp ../pulpcore/.travis/pulp-smash-config.json ~/.config/pulp_smash/settings.json


if [ -f $POST_BEFORE_SCRIPT ]; then
    $POST_BEFORE_SCRIPT
fi
