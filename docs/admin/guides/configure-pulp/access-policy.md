# Access Policies

Pulp uses [access policies] to define which circumstances including permissions are necessary for certain api accesses.

!!! warning
    Access policies are at the core of Pulp's decision process whether an action should be permitted or denied.
    It is possible to allow or restrict almost everything that way.
    We cannot prevent you from making dangerous mistakes here.
    Great care should be taken when touching any of this.

!!! note
    The method described here needs the _non-default_ permission class `AccessPolicyFromSettings` to be configured for DRF.

In order to deviate from the provided default access policy on a specific viewset, you first need to find the corresponding `urlpattern`:

```ipython
In [1]: from pulpcore.app.viewsets import ListContentViewSet

In [2]: ListContentViewSet.urlpattern()
Out[2]: 'content'
```

Then you should start looking at the default access policy:

```ipython
In [4]: ListContentViewSet.DEFAULT_ACCESS_POLICY
Out[4]: 
{'statements': [{'action': ['list'],
   'principal': 'authenticated',
   'effect': 'allow'}],
 'queryset_scoping': {'function': 'scope_queryset'}}
```

Add this to your settings (e.g. in setting.py):

```python
ACCESS_POLICIES = {
    "content": {
        "statements": [
            {"action": ["list"], "principal": "authenticated", "effect": "allow"}
        ],
        "queryset_scoping": {"function": "scope_queryset"},
    },
}
```

And start to modify it there.
You can use the helper functions defined in `pulpcore.app.global_access_conditions`.
Some plugins provide even more of them.

!!! note
    The api services need to be restarted for this to take effect.

[access policies]: https://rsinger86.github.io/drf-access-policy/
