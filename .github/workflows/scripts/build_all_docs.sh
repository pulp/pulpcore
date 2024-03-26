# This script builds the documentation site for staging-docs.pulpproject.org
pip install git+https://github.com/pulp/pulp-docs.git
pulp-docs build
tar cvf staging-docs.pulpproject.org.tar ./site
