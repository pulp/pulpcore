# This script builds the documentation site for staging-docs.pulpproject.org
pip install git+https://github.com/pedro-psb/pulp-docs.git
pulp-docs build
tar cvf staging-docs.pulpproject.org.tar ./site
