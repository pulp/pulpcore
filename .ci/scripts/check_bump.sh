#!/bin/bash

set -eux
bump-my-version bump release --dry-run --allow-dirty
bump-my-version show-bump
