# Complex Filtering

!!! warning
This feature is in tech-preview. It may change in significant ways in the future.


In addition to the usual querystring filters, Pulp provides a special `q` filter, that allows you
to combine other filters with `NOT`, `AND` and `OR` operations.

!!! warning
In order to prevent arbitrarily complex queries, the maximum complexity of the expressions
explained below is limited to 8. See the examples below for how complexity is calculated.


For a given list endpoint, all the other existing (non ordering) filters can be used in these
expressions.

The grammar, given sufficient whitespace to tokenize, is basically:

```
EXPRESSION = FILTER_EXPR | NOT_EXPR | AND_EXPR | OR_EXPR | "(" EXPRESSION ")"
NOT_EXPR = "NOT" EXPRESSION
AND_EXPRESSION = EXPRESSION "AND" EXPRESSION
OR_EXPRESSION = EXPRESSION "OR" EXPRESSION
FILTER_EXPRESSION = FILTERNAME "=" STRING
STRING = SIMPLE_STRING | QUOTED_STRING
```

Some example `q` expressions and their complexity are:

```
pulp_type__in='core.rbac'
# complexity: 1 = 1 (filter expression)

NOT pulp_type="core.rbac"
# complexity: 2 = 1 (NOT) + 1 (filter expression)

pulp_type__in=core.rbac,core.content_redirect
# complexity: 1 = 1 (filter expression)

pulp_type="core.rbac" OR pulp_type="core.content_redirect"
pulp_type="core.rbac" AND name__contains=GGGG
pulp_type="core.rbac" AND name__iexact=gGgG
pulp_type="core.rbac" AND name__contains="naïve"
# complexity: 3 = 1 (AND/OR) + 2 (filter expression)

pulp_type="core.rbac" AND name__icontains=gg AND NOT name__contains=HH
# complexity: 5 = 1 (AND/OR) + 1 (NOT) + 3 (filter expression)

NOT (pulp_type="core.rbac" AND name__icontains=gGgG)
pulp_type="core.rbac" AND NOT name__contains="naïve"
# complexity: 4 = 1 (AND/OR) + 1 (NOT) + 2 (filter expression)

pulp_type="core.rbac" AND(   name__icontains=gh OR name__contains="naïve")
# complexity: 5 = 2 (AND/OR) + 3 (filter expression)

pulp_type="core.rbac" OR name__icontains=gh OR name__contains="naïve"
# complexity: 4 = 1 (AND/OR) + 3 (filter expression)
```
