#!/usr/bin/env bash
# coding=utf-8

set -mveuo pipefail

export PYTHONPATH=$TRAVIS_BUILD_DIR/../pulp_file:$TRAVIS_BUILD_DIR/../pulp-certguard:${PYTHONPATH}

pytest -v -r sx --color=yes --pyargs pulpcore.tests.functional
pytest -v -r sx --color=yes --pyargs pulp_file.tests.functional
pytest -v -r sx --color=yes --pyargs pulp_certguard.tests.functional
