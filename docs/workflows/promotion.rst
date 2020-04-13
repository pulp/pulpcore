Promotion
=========

A typical workflow for several users of Pulp is managing separate sets of content for different
lifecycle environments (e.g. Dev, Staging, Production, etc) and promoting content from one
environment to another. There are some features Pulp provides which can help facilitate this.

Distributions
-------------

:term:`Distributions<Distribution>` are a resource in Pulp that are useful for supporting different
environments. In most cases, you'll want to create one Distribution for each :term:`Repository` and
environment. If for example, you have a CentOS Repository that you want to serve to your Dev
servers, you can create a distribution called "Dev CentOS" that points to your CentOS Publication.

One way to promote content is to use Distributions. Going back to the Dev CentOS example one way you
could promote this Publication to a Staging environment would be to create a Staging CentOS
distribution and point it to the same publication as the Dev CentOS distribution. Any time you want
to promote content from Dev to Staging, you can simply repeat this action. Also, to rollback, you can
simply point the Staging CentOS distribution to the Publication it was previously pointed at.

Repositories
------------

Another way to promote content is to create separate Repositories for each environment. This gives
you greater control over which content is available to each environment. In the case where you want
to make a CentOS Repository available to Dev and Production environments, you'd create two
Repositories: a Dev CentOS and a Production CentOS Repository. You'd also create one Distribution
for each repository and you'd sync down all content from a Remote into the Dev CentOS Repository and
only that Repository.

When you want to promote content from Dev to Production, one option is to call the ``modify``
endpoint on the Production CentOS Repository and supply a Dev CentOS RepositoryVersion as the
``base_version`` parameter. This will copy all content from the Dev CentOS RepositoryVersion of your
choosing into the Production CentOS repository.

This method of managing environment content is particularly useful for plugins without Publications
where Distributions can point directly to a Repository.
