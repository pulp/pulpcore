#!/usr/bin/env bash
# coding=utf-8

set -mveuo pipefail

# Temporarily need to downgrade pulp-smash to run pulpcore 3.9 tests
pip install 'pulp-smash==1!0.12.0'

pytest -v -r sx --color=yes --pyargs pulpcore.tests.functional
