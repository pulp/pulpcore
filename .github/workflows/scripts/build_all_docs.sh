# This script builds the documentation site for staging-docs.pulpproject.org
pip install git+https://github.com/pulp/pulp-docs.git
cd ..
pulp-docs build
tar cvf pulpcore/staging-docs.pulpproject.org.tar ./site
cd pulpcore
