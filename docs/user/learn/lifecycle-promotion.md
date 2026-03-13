# Lifecyle Promotion Support

A typical workflow for several users of Pulp is managing separate sets of content for different
lifecycle environments (e.g. Dev, Staging, Production, etc) and promoting content from one
environment to another. There are some features Pulp provides which can help facilitate this.

## Distributions

`Distributions` are a resource in Pulp that are useful for supporting different environments.
A Distribution can serve content by pointing to a `Repository` (automatically serving the latest
version), a `RepositoryVersion` (serving a specific version), or for content types that use
publications, a specific `Publication`.

In most cases, you'll want to create one Distribution for each `Repository` and environment.
If for example, you have a CentOS Repository that you want to serve to your Dev servers,
you can create a distribution called "Dev CentOS" that points to a specific `RepositoryVersion`
of your CentOS Repository.

One way to promote content is to use Distributions. Going back to the Dev CentOS example,
one way you could promote content to a Staging environment would be to create a Staging CentOS
distribution and point it to the same `RepositoryVersion` as the Dev CentOS distribution.
Any time you want to promote content from Dev to Staging, you can simply repeat this action.
To rollback, simply point the Staging CentOS distribution to the `RepositoryVersion` it was
previously pointed at. For content types that use publications, you can also point distributions
at a specific `Publication`.

## Repositories

Another way to promote content is to create separate Repositories for each environment. This gives
you greater control over which content is available to each environment. In the case where you want
to make a CentOS Repository available to Dev and Production environments, you'd create two
Repositories: a Dev CentOS and a Production CentOS Repository. You'd also create one Distribution
for each repository and you'd sync down all content from a Remote into the Dev CentOS Repository and
only that Repository.

When you want to promote content from Dev to Production, one option is to call the `modify`
endpoint on the Production CentOS Repository and supply a Dev CentOS RepositoryVersion as the
`base_version` parameter. This will copy all content from the Dev CentOS RepositoryVersion of your
choosing into the Production CentOS repository.

This method of managing environment content is particularly useful for plugins without Publications
where Distributions can point directly to a Repository.
