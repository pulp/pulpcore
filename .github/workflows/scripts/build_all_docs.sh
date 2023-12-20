# This script builds the documentation site for staging-docs.pulpproject.org
mkdir site
echo 'New Pulp Docs!' > site/index.html
tar cvf staging-docs.pulpproject.org.tar ./site
