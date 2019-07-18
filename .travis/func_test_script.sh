#!/usr/bin/env bash
# coding=utf-8

set -mveuo pipefail

pytest -v -r sx --color=yes --pyargs pulpcore.tests.functional || show_logs_and_return_non_zero
pytest -v -r sx --color=yes --pyargs pulp_file.tests.functional || show_logs_and_return_non_zero
pytest -v -r sx --color=yes --pyargs pulp_certguard.tests.functional || show_logs_and_return_non_zero
