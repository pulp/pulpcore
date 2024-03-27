# This script builds the documentation site for staging-docs.pulpproject.org

# TODO: this chdir move is a tmp workaround. Remove when no longer needed.
# see: https://github.com/mkdocstrings/python/issues/145
mkdir ../build_dir && pushd ../build_dir

pip install git+https://github.com/pulp/pulp-docs.git
pulp-docs build
tar cvf ../pulpcore/staging-docs.pulpproject.org.tar site

popd
