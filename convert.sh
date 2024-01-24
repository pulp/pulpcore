#!/bin/bash

find staging_docs -type f -name "*.md" -exec sed -i -e 's/:::{note}/!!! note/' {} ';'
find staging_docs -type f -name "*.md" -exec sed -i -e 's/:::{tip}/!!! tip/' {} ';'
find staging_docs -type f -name "*.md" -exec sed -i -e 's/:::{warning}/!!! warning/' {} ';'
find staging_docs -type f -name "*.md" -exec sed -i -e 's/:::{hint}/!!! tip/' {} ';'
find staging_docs -type f -name "*.md" -exec sed -i -e 's/:::{glossary}//' {} ';'
find staging_docs -type f -name "*.md" -exec sed -i -e 's/:::$//' {} ';'
